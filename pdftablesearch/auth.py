"""Cookie-backed login and idle-session enforcement for the web API."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request
from starlette.responses import Response

from pdftablesearch.config import get_settings

AUTH_COOKIE = "pdf_portal_auth"
AUTH_PRESENCE_COOKIE = "pdf_portal_auth_presence"


@dataclass
class AuthUser:
    user_id: str
    username: str
    name: str
    department_id: str = ""
    roles: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "name": self.name,
            "department_id": self.department_id,
            "roles": list(self.roles),
        }


@dataclass
class AuthSession:
    token: str
    user: AuthUser
    issued_at: float
    expires_at: float
    last_activity: float


@dataclass
class PreAuthSession:
    token: str
    user: AuthUser
    issued_at: float
    expires_at: float


_auth_sessions: Dict[str, AuthSession] = {}
_pre_auth_sessions: Dict[str, PreAuthSession] = {}


def auth_config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "enabled": settings.auth_enabled,
        "idle_timeout_seconds": settings.auth_idle_timeout_seconds,
        "warn_before_seconds": settings.auth_warn_before_seconds,
        "session_ttl_seconds": settings.auth_session_ttl_seconds,
        "pre_auth_ttl_seconds": settings.auth_pre_auth_ttl_seconds,
    }


def create_pre_auth_session(user: AuthUser) -> PreAuthSession:
    settings = get_settings()
    now = time.time()
    token = secrets.token_urlsafe(32)
    session = PreAuthSession(
        token=token,
        user=user,
        issued_at=now,
        expires_at=now + settings.auth_pre_auth_ttl_seconds,
    )
    _pre_auth_sessions[token] = session
    return session


def verify_otp(pre_auth_token: str, otp_code: str) -> AuthUser:
    settings = get_settings()
    session = _pre_auth_sessions.get(pre_auth_token)
    now = time.time()
    if session is None or session.expires_at <= now:
        if session is not None:
            _pre_auth_sessions.pop(pre_auth_token, None)
        raise HTTPException(status_code=401, detail="OTP session expired")

    expected = settings.auth_otp_code.strip()
    submitted = otp_code.strip()
    if not expected or not secrets.compare_digest(expected, submitted):
        _pre_auth_sessions.pop(pre_auth_token, None)
        raise HTTPException(status_code=401, detail="Invalid OTP code")

    _pre_auth_sessions.pop(pre_auth_token, None)
    return session.user


def create_auth_session(user: AuthUser) -> AuthSession:
    settings = get_settings()
    now = time.time()
    token = secrets.token_urlsafe(32)
    session = AuthSession(
        token=token,
        user=user,
        issued_at=now,
        expires_at=now + settings.auth_session_ttl_seconds,
        last_activity=now,
    )
    _auth_sessions[token] = session
    return session


def get_auth_session(token: Optional[str]) -> Optional[AuthSession]:
    if not token:
        return None
    return _auth_sessions.get(token)


def validate_auth_request(request: Request) -> Optional[AuthSession]:
    settings = get_settings()
    if not settings.auth_enabled:
        return None

    token = request.cookies.get(AUTH_COOKIE)
    session = get_auth_session(token)
    if session is None:
        return None

    now = time.time()
    if session.expires_at <= now or now - session.last_activity > settings.auth_idle_timeout_seconds:
        _auth_sessions.pop(session.token, None)
        return None

    session.last_activity = now
    return session


def end_auth_session(token: Optional[str]) -> None:
    if token:
        _auth_sessions.pop(token, None)


def set_auth_cookies(response: Response, session: AuthSession) -> None:
    settings = get_settings()
    max_age = int(max(0, session.expires_at - time.time()))
    response.set_cookie(
        AUTH_COOKIE,
        session.token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        AUTH_PRESENCE_COOKIE,
        "1",
        max_age=max_age,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE, path="/")
    response.delete_cookie(AUTH_PRESENCE_COOKIE, path="/")


def authenticate_login(username: str, password: str) -> AuthUser:
    settings = get_settings()
    if settings.ldap_server:
        return _authenticate_ldap(username=username, password=password)
    return _authenticate_dev_user(username=username, password=password)


def _authenticate_dev_user(username: str, password: str) -> AuthUser:
    settings = get_settings()
    for entry in settings.auth_dev_users.split(","):
        fields = [field.strip() for field in entry.split(":")]
        if len(fields) < 2:
            continue
        user, expected = fields[0], fields[1]
        if not secrets.compare_digest(user, username):
            continue
        if not secrets.compare_digest(expected, password):
            break
        name = fields[2] if len(fields) >= 3 and fields[2] else username
        roles = tuple(
            role.strip()
            for role in (fields[3].split("|") if len(fields) >= 4 else ["user"])
            if role.strip()
        )
        return AuthUser(user_id=username, username=username, name=name, roles=roles)
    raise HTTPException(status_code=401, detail="Invalid username or password")


def _authenticate_ldap(username: str, password: str) -> AuthUser:
    settings = get_settings()
    if not password:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    try:
        from ldap3 import ALL, Connection, Server
        from ldap3.utils.conv import escape_filter_chars
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="ldap3 dependency is not installed") from exc

    server = Server(settings.ldap_server, get_info=ALL)
    bind_kwargs: dict[str, Any] = {"auto_bind": True}
    if settings.ldap_bind_dn:
        bind_kwargs["user"] = settings.ldap_bind_dn
        bind_kwargs["password"] = settings.ldap_bind_password or ""

    try:
        service_conn = Connection(server, **bind_kwargs)
        user_filter = settings.ldap_user_filter.format(
            username=escape_filter_chars(username)
        )
        found = service_conn.search(
            search_base=settings.ldap_base_dn,
            search_filter=user_filter,
            attributes=[
                settings.ldap_name_attr,
                settings.ldap_department_attr,
                settings.ldap_roles_attr,
            ],
            size_limit=1,
        )
        if not found or not service_conn.entries:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        entry = service_conn.entries[0]
        user_dn = entry.entry_dn
        service_conn.unbind()

        user_conn = Connection(server, user=user_dn, password=password, auto_bind=True)
        user_conn.unbind()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid username or password") from exc

    name = _entry_value(entry, settings.ldap_name_attr) or username
    department_id = _entry_value(entry, settings.ldap_department_attr) or ""
    raw_roles = _entry_values(entry, settings.ldap_roles_attr)
    roles = tuple(raw_roles) if raw_roles else ("user",)
    return AuthUser(
        user_id=username,
        username=username,
        name=name,
        department_id=department_id,
        roles=roles,
    )


def _entry_value(entry: Any, attr: str) -> str:
    values = _entry_values(entry, attr)
    return values[0] if values else ""


def _entry_values(entry: Any, attr: str) -> list[str]:
    try:
        value = getattr(entry, attr)
    except Exception:
        return []
    try:
        values = value.values
    except Exception:
        raw = str(value) if value is not None else ""
        return [raw] if raw else []
    return [str(item) for item in values if str(item)]
