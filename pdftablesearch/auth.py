"""LDAP authentication and JWT cookie helpers for the FastAPI app."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import jwt
import ldap3
from fastapi import Header, HTTPException, Request, Response
from ldap3.core.exceptions import LDAPBindError, LDAPException
from ldap3.utils.conv import escape_filter_chars
from pydantic import BaseModel, Field

from pdftablesearch.config import get_settings
from pdftablesearch.session_store import read_session

logger = logging.getLogger(__name__)

_INSECURE_DEFAULT_SECRET = "dev-secret-change-me"
_DEFAULT_OTP_JAR_PATH = "packages/api/lib/otp-cli.jar"
_DEFAULT_OTP_SDK_JAR_NAME = "certifyOtp.jar"
_OTP_MAIN_CLASS = "OtpCli"
_OTP_KILL_WAIT_SECONDS = 1


class LDAPUser(BaseModel):
    """Authenticated user information derived from LDAP."""

    user_id: str
    username: str
    name: str | None = None
    email: str | None = None
    department: str | None = None
    roles: list[str] = Field(default_factory=list)


class LDAPClient:
    """Authenticate users via service-account bind followed by user bind."""

    def __init__(
        self,
        server: str,
        base_dn: str,
        service_bind_dn: str,
        service_bind_password: str,
        user_filter: str,
        attr_map: dict[str, str],
        use_tls: bool = False,
        strategy: str = ldap3.SYNC,
    ) -> None:
        self._server = ldap3.Server(server, use_ssl=use_tls, get_info=ldap3.NONE)
        self._base_dn = base_dn
        self._service_bind_dn = service_bind_dn
        self._service_bind_password = service_bind_password
        self._user_filter = user_filter
        self._attr_map = attr_map
        self._strategy = strategy

    def authenticate(self, username: str, password: str) -> LDAPUser | None:
        """Return the LDAP user on success, otherwise ``None``."""
        username = username.strip()
        if not username or not password:
            return None

        service_conn = self._bind_service_account()
        if service_conn is None:
            return None

        try:
            attrs = list(dict.fromkeys(self._attr_map.values()))
            escaped_username = escape_filter_chars(username)
            search_filter = self._user_filter.format(username=escaped_username)
            service_conn.search(self._base_dn, search_filter, attributes=attrs)
            if not service_conn.entries:
                return None

            entry = service_conn.entries[0]
            user_dn = entry.entry_dn
            user_attrs = self._extract_attrs(entry)
        finally:
            service_conn.unbind()

        try:
            user_conn = ldap3.Connection(
                self._server,
                user=user_dn,
                password=password,
                client_strategy=self._strategy,  # type: ignore[arg-type]
                auto_bind=ldap3.AUTO_BIND_NO_TLS,
            )
            if not user_conn.bind():
                return None
        except LDAPBindError:
            return None
        except LDAPException:
            return None
        else:
            user_conn.unbind()

        return LDAPUser(
            user_id=username,
            username=username,
            name=user_attrs.get("name") or username,
            email=user_attrs.get("email"),
            department=user_attrs.get("department"),
            roles=user_attrs.get("roles", []),
        )

    def _bind_service_account(self) -> ldap3.Connection | None:
        try:
            conn = ldap3.Connection(
                self._server,
                user=self._service_bind_dn,
                password=self._service_bind_password,
                client_strategy=self._strategy,  # type: ignore[arg-type]
                auto_bind=ldap3.AUTO_BIND_NO_TLS,
            )
        except LDAPException:
            return None
        if not conn.bind():
            return None
        return conn

    def _extract_attrs(self, entry: Any) -> dict[str, Any]:
        def _values(ldap_attr: str) -> list[str]:
            value = getattr(entry, ldap_attr, None)
            if value is None:
                return []
            if hasattr(value, "values"):
                return [str(v) for v in value.values if v is not None]
            return [str(value)]

        role_values = _values(self._attr_map.get("role", "title"))
        return {
            "name": next(iter(_values(self._attr_map.get("name", "cn"))), None),
            "email": next(iter(_values(self._attr_map.get("email", "mail"))), None),
            "department": next(
                iter(_values(self._attr_map.get("department", "departmentNumber"))),
                None,
            ),
            "roles": role_values,
        }


def ldap_client_from_settings() -> LDAPClient:
    """Construct the LDAP client from environment-backed settings."""
    settings = get_settings()
    missing = [
        key
        for key, value in (
            ("LDAP_SERVER_URL", settings.ldap_server_url),
            ("LDAP_BASE_DN", settings.ldap_base_dn),
            ("LDAP_SERVICE_BIND_DN", settings.ldap_service_bind_dn),
            ("LDAP_SERVICE_BIND_PASSWORD", settings.ldap_service_bind_password),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "LDAP authentication is not fully configured. Missing: "
            + ", ".join(missing)
        )

    return LDAPClient(
        server=settings.ldap_server_url,
        base_dn=settings.ldap_base_dn,
        service_bind_dn=settings.ldap_service_bind_dn,
        service_bind_password=settings.ldap_service_bind_password,
        user_filter=settings.ldap_user_filter,
        attr_map={
            "name": settings.ldap_attr_name,
            "email": settings.ldap_attr_email,
            "department": settings.ldap_attr_department,
            "role": settings.ldap_attr_role,
        },
        use_tls=settings.ldap_use_tls,
    )


def _secret() -> str:
    settings = get_settings()
    return (
        os.getenv("AUTH_SECRET_KEY")
        or os.getenv("CHAINLIT_AUTH_SECRET")
        or settings.auth_secret_key
    )


def _issue(payload: dict[str, Any], ttl_seconds: int) -> str:
    now = int(time.time())
    full = {**payload, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(full, _secret(), algorithm="HS256")


def _decode(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def _pre_auth_ttl() -> int:
    settings = get_settings()
    is_dev = settings.app_env.lower() == "dev"
    value = (
        settings.auth_pre_auth_ttl_dev_seconds
        if is_dev
        else settings.auth_pre_auth_ttl_seconds
    )
    return value if value > 0 else 300


def issue_pre_auth_jwt(user: LDAPUser | dict[str, Any]) -> str:
    """Issue a short-lived JWT after LDAP succeeds, before OTP verification."""
    user_data = user.model_dump() if isinstance(user, LDAPUser) else user
    return _issue({"sub": "pre_auth", "jti": uuid.uuid4().hex, **user_data}, _pre_auth_ttl())


def decode_pre_auth_jwt(token: str) -> dict[str, Any] | None:
    """Return user claims from a valid pre-auth JWT."""
    payload = _decode(token)
    if not payload or payload.get("sub") != "pre_auth":
        return None
    return {
        key: value
        for key, value in payload.items()
        if key not in {"sub", "iat", "exp", "jti"}
    }


def issue_session_jwt(user: LDAPUser | dict[str, Any]) -> tuple[str, int, str]:
    """Issue a signed session JWT and return ``(token, ttl_seconds, jti)``."""
    settings = get_settings()
    user_data = user.model_dump() if isinstance(user, LDAPUser) else user
    ttl_seconds = max(1, settings.auth_token_expire_hours) * 3600
    jti = uuid.uuid4().hex
    token = _issue({"sub": "session", "jti": jti, **user_data}, ttl_seconds)
    return token, ttl_seconds, jti


def issue_auth_token(user: LDAPUser) -> tuple[str, int]:
    """Compatibility wrapper returning ``(token, ttl_seconds)``."""
    token, ttl_seconds, _ = issue_session_jwt(user)
    return token, ttl_seconds


def auth_config() -> dict[str, int]:
    """Return public browser-side auth timing configuration."""
    settings = get_settings()
    idle_timeout = (
        settings.auth_idle_timeout_dev_seconds
        if settings.app_env.lower() == "dev"
        else settings.auth_idle_timeout_seconds
    )
    if idle_timeout <= 0:
        idle_timeout = 600
    warn_before = settings.auth_warn_before_seconds if settings.auth_warn_before_seconds > 0 else 30
    return {
        "idle_timeout_seconds": idle_timeout,
        "warn_before_seconds": warn_before,
    }


def client_ip(request: Request) -> str:
    """Extract client IP in the same way as analytics_agent."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


def _build_otp_command(
    company_code: str,
    user_id: str,
    otp: str,
    asstsq: str,
    client_ip_str: str,
) -> list[str]:
    settings = get_settings()
    jar_path = str(settings.otp_jar_path or _DEFAULT_OTP_JAR_PATH)
    sdk_path = str(settings.otp_sdk_path or Path(jar_path).with_name(_DEFAULT_OTP_SDK_JAR_NAME))
    if Path(sdk_path).expanduser().exists():
        classpath = os.pathsep.join([jar_path, sdk_path])
        return ["java", "-cp", classpath, _OTP_MAIN_CLASS, company_code, user_id, otp, asstsq, client_ip_str]
    return ["java", "-jar", jar_path, company_code, user_id, otp, asstsq, client_ip_str]


async def _kill_subprocess(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.wait(), timeout=_OTP_KILL_WAIT_SECONDS)


async def call_otp_subprocess(user_id: str, otp: str, client_ip_str: str) -> str:
    """Call the Java OTP CLI and return its result code.

    The expected stdout contract matches analytics_agent: ``"0"`` means
    success, ``"6000"`` means failed OTP, and every system problem returns
    ``"error"``.
    """
    settings = get_settings()
    company_code = (
        settings.otp_company_code_dev
        if settings.app_env.lower() == "dev"
        else settings.otp_company_code_prod
    )
    cmd = _build_otp_command(
        company_code=company_code,
        user_id=user_id,
        otp=otp,
        asstsq=settings.otp_asstsq,
        client_ip_str=client_ip_str,
    )
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(),
            timeout=max(1, settings.otp_timeout_seconds),
        )
        if proc.returncode != 0:
            return "error"
        return stdout.decode().strip()
    except TimeoutError:
        if proc is not None:
            await _kill_subprocess(proc)
        return "error"
    except Exception:
        if proc is not None:
            await _kill_subprocess(proc)
        return "error"


def decode_session_claims(token: str) -> dict[str, Any] | None:
    """Validate JWT signature/expiry and return session claims."""
    payload = _decode(token)
    if not payload or payload.get("sub") != "session":
        return None
    return {
        key: value
        for key, value in payload.items()
        if key not in {"sub", "iat", "exp"}
    }


def decode_auth_token(token: str) -> LDAPUser | None:
    """Validate and decode a session token without checking Redis."""
    payload = decode_session_claims(token)
    if payload is None:
        return None
    claims = {
        key: value
        for key, value in payload.items()
        if key != "jti"
    }
    try:
        return LDAPUser.model_validate(claims)
    except Exception:
        return None


def set_auth_cookie(response: Response, token: str, ttl_seconds: int) -> None:
    """Persist the auth token in an httpOnly cookie."""
    settings = get_settings()
    secure = settings.auth_cookie_secure_dev if settings.app_env.lower() == "dev" else settings.auth_cookie_secure
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=ttl_seconds,
        httponly=True,
        secure=secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key="auth_presence",
        value="1",
        httponly=False,
        secure=secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Delete auth cookies."""
    settings = get_settings()
    secure = settings.auth_cookie_secure_dev if settings.app_env.lower() == "dev" else settings.auth_cookie_secure
    response.delete_cookie(
        key=settings.auth_cookie_name,
        secure=secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )
    response.delete_cookie(
        key="auth_presence",
        secure=secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> LDAPUser:
    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if token is None and authorization and isinstance(authorization, str) and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token_claims = decode_session_claims(token)
    if token_claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    claims = await read_session(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    if claims.get("jti") != token_claims.get("jti"):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    try:
        return LDAPUser.model_validate(
            {k: v for k, v in claims.items() if k not in {"jti", "_ttl"}}
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session data") from None


def warn_if_insecure_auth_secret() -> None:
    """Reject the baked-in JWT secret outside explicit local development."""
    settings = get_settings()
    if settings.auth_secret_key == _INSECURE_DEFAULT_SECRET and settings.app_env.lower() not in {
        "dev",
        "local",
        "test",
    }:
        raise RuntimeError(
            "AUTH_SECRET_KEY is using the development default. Set a strong secret before "
            "running LDAP authentication outside local development."
        )
    if settings.auth_secret_key == _INSECURE_DEFAULT_SECRET:
        logger.warning(
            "AUTH_SECRET_KEY is using the development default. "
            "Set a strong secret before deploying beyond local development."
        )
