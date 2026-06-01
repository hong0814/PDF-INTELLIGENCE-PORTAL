"""LDAP authentication and JWT cookie helpers for the FastAPI app."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import jwt
import ldap3
from fastapi import Header, HTTPException, Request, Response
from ldap3.core.exceptions import LDAPBindError, LDAPException
from ldap3.utils.conv import escape_filter_chars
from pydantic import BaseModel, Field

from pdftablesearch.config import get_settings

logger = logging.getLogger(__name__)

_INSECURE_DEFAULT_SECRET = "dev-secret-change-me"


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


def issue_auth_token(user: LDAPUser) -> tuple[str, int]:
    """Issue a signed session token and return ``(token, ttl_seconds)``."""
    settings = get_settings()
    ttl_seconds = max(1, settings.auth_token_expire_hours) * 3600
    now = int(time.time())
    payload = {
        "sub": "session",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + ttl_seconds,
        **user.model_dump(),
    }
    token = jwt.encode(payload, settings.auth_secret_key, algorithm="HS256")
    return token, ttl_seconds


def decode_auth_token(token: str) -> LDAPUser | None:
    """Validate and decode a session token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    if payload.get("sub") != "session":
        return None

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
    authorization: str | None = Header(default=None),
) -> LDAPUser:
    """Return the authenticated user from cookie or bearer token."""
    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if token is None and authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = decode_auth_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


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
