"""LDAP authentication and JWT cookie helpers for the FastAPI app."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
import ldap3
from fastapi import Header, HTTPException, Request, Response
from ldap3.core.exceptions import LDAPBindError, LDAPException
from ldap3.utils.conv import escape_filter_chars
from pydantic import BaseModel, Field

from pdftablesearch.config import get_settings
from pdftablesearch.session_store import (
    delete_session,
    read_session,
    write_session,
)

logger = logging.getLogger(__name__)

_INSECURE_DEFAULT_SECRET = "dev-secret-change-me"

_DEFAULT_OTP_JAR_PATH = "packages/api/lib/otp-cli.jar"
_OTP_MAIN_CLASS = "OtpCli"
_OTP_KILL_WAIT_SECONDS = 1


# ---------------------------------------------------------------------------
# Idle timeout helpers (Redis-backed)
# ---------------------------------------------------------------------------

async def _is_session_active(token: str, jti: str) -> bool:
    """Check whether a session token is still valid in Redis (not idle-expired)."""
    claims = await read_session(token)
    if claims is None:
        return False
    stored_jti = claims.get("jti", "")
    if stored_jti != jti:
        return False
    return True


async def _touch_session(token: str, jti: str) -> bool:
    """Ping Redis to extend idle timeout without changing token TTL."""
    claims = await read_session(token)
    if claims is None:
        return False
    stored_jti = claims.get("jti", "")
    if stored_jti != jti:
        return False
    settings = get_settings()
    remaining_ttl = max(1, settings.auth_session_ttl_seconds)
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=["HS256"])
    except Exception:
        return False
    return await write_session(token, {**claims, "jti": jti}, remaining_ttl)


async def _end_session(token: str) -> None:
    """Remove session token from Redis."""
    await delete_session(token)




def auth_config_dict() -> dict[str, Any]:
    settings = get_settings()
    enabled = bool(settings.ldap_server_url)
    return {
        "enabled": enabled,
        "idle_timeout_seconds": settings.auth_idle_timeout_seconds,
        "warn_before_seconds": settings.auth_warn_before_seconds,
        "session_ttl_seconds": settings.auth_session_ttl_seconds,
    }


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


# ---------------------------------------------------------------------------
# JWT encode/decode helpers
# ---------------------------------------------------------------------------

def _secret() -> str:
    settings = get_settings()
    return os.getenv("AUTH_SECRET_KEY") or settings.auth_secret_key


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


def issue_pre_auth_jwt(user: LDAPUser | dict[str, Any]) -> str:
    settings = get_settings()
    user_data = user.model_dump() if isinstance(user, LDAPUser) else user
    ttl = settings.auth_pre_auth_ttl_seconds
    return _issue({"sub": "pre_auth", "jti": uuid.uuid4().hex, **user_data}, ttl)


def decode_pre_auth_jwt(token: str) -> dict[str, Any] | None:
    payload = _decode(token)
    if not payload or payload.get("sub") != "pre_auth":
        return None
    return {
        key: value
        for key, value in payload.items()
        if key not in {"sub", "iat", "exp", "jti"}
    }


def issue_session_jwt(user: LDAPUser | dict[str, Any]) -> tuple[str, int, str]:
    settings = get_settings()
    user_data = user.model_dump() if isinstance(user, LDAPUser) else user
    ttl_seconds = max(1, settings.auth_token_expire_hours) * 3600
    jti = uuid.uuid4().hex
    token = _issue({"sub": "session", "jti": jti, **user_data}, ttl_seconds)
    return token, ttl_seconds, jti


async def issue_auth_token(user: LDAPUser) -> tuple[str, int]:
    token, ttl_seconds, jti = issue_session_jwt(user)
    await write_session(token, {**user.model_dump(), "jti": jti}, ttl_seconds)
    return token, ttl_seconds


async def decode_auth_token(token: str) -> LDAPUser | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    if await read_session(token) is None:
        return None

    jti = payload.get("jti", "")
    if not await _is_session_active(token, jti):
        return None

    await _touch_session(token, jti)

    claims = {
        key: value
        for key, value in payload.items()
        if key not in {"sub", "iat", "exp", "jti"}
    }
    try:
        return LDAPUser.model_validate(claims)
    except Exception:
        return None


def set_auth_cookie(response: Response, token: str, ttl_seconds: int) -> None:
    """Persist the auth token in an httpOnly cookie."""
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Delete the auth cookie."""
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        secure=settings.auth_cookie_secure,
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

    user = await decode_auth_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


async def touch_auth_session(request: Request) -> bool:
    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return False
    jti = payload.get("jti", "")
    if not await _is_session_active(token, jti):
        return False
    return await _touch_session(token, jti)


async def end_auth_session(request: Request) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return
    await _end_session(token)


# ---------------------------------------------------------------------------
# OTP helpers
# ---------------------------------------------------------------------------

def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


async def call_otp_verify(user_id: str, otp: str, client_ip_str: str) -> str:
    settings = get_settings()
    if settings.app_env.lower() in ("dev", "local", "test") and settings.otp_mock_enabled:
        logger.info("OTP mock enabled: skipping Java OTP for user=%s", user_id)
        return "0"

    cmd = ["java", "-jar", str(settings.otp_jar_path), settings.otp_company_code, user_id, otp, settings.otp_asstsq, client_ip_str]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=settings.otp_timeout_seconds)
        if proc.returncode != 0:
            return "error"
        return stdout.decode().strip()
    except asyncio.TimeoutError:
        await _kill_subprocess(proc)
        return "error"
    except Exception:
        await _kill_subprocess(proc)
        return "error"


async def _kill_subprocess(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.wait(), timeout=_OTP_KILL_WAIT_SECONDS)


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
