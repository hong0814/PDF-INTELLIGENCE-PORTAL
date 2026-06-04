from fastapi.testclient import TestClient

from pdftablesearch.auth import (
    AUTH_COOKIE,
    AUTH_PRESENCE_COOKIE,
    _auth_sessions,
    _pre_auth_sessions,
)
from pdftablesearch.config import get_settings
from pdftablesearch.web_server import app


def setup_function() -> None:
    _auth_sessions.clear()
    _pre_auth_sessions.clear()


def teardown_function() -> None:
    _auth_sessions.clear()
    _pre_auth_sessions.clear()


def _start_login(
    client: TestClient,
    *,
    username: str = "admin",
    password: str = "admin",
) -> str:
    login = client.post(
        "/api/auth/ldap",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["authenticated"] is False
    assert body["requires_otp"] is True
    assert body["user"]["username"] == username
    assert body["pre_auth_ttl_seconds"] == get_settings().auth_pre_auth_ttl_seconds
    assert not client.cookies.get(AUTH_COOKIE)
    assert not client.cookies.get(AUTH_PRESENCE_COOKIE)
    return body["pre_auth_token"]


def _complete_login(
    client: TestClient,
    *,
    username: str = "admin",
    password: str = "admin",
) -> str:
    pre_auth_token = _start_login(client, username=username, password=password)
    otp = client.post(
        "/api/auth/otp",
        json={
            "pre_auth_token": pre_auth_token,
            "otp_code": get_settings().auth_otp_code,
        },
    )
    assert otp.status_code == 200
    assert otp.json()["authenticated"] is True
    assert pre_auth_token not in _pre_auth_sessions
    token = client.cookies.get(AUTH_COOKIE)
    assert token
    assert client.cookies.get(AUTH_PRESENCE_COOKIE) == "1"
    return token


def test_auth_config_is_public() -> None:
    client = TestClient(app)

    response = client.get("/api/auth/config")

    assert response.status_code == 200
    body = response.json()
    assert body["idle_timeout_seconds"] == get_settings().auth_idle_timeout_seconds
    assert body["pre_auth_ttl_seconds"] == get_settings().auth_pre_auth_ttl_seconds


def test_api_requires_login() -> None:
    client = TestClient(app)

    response = client.get("/api/sessions")

    assert response.status_code == 401


def test_ldap_login_returns_pre_auth_token_without_cookies() -> None:
    client = TestClient(app)

    pre_auth_token = _start_login(client)

    assert pre_auth_token in _pre_auth_sessions

    response = client.get("/api/sessions")

    assert response.status_code == 401


def test_otp_sets_cookies_and_allows_api() -> None:
    client = TestClient(app)

    _complete_login(client)

    response = client.get("/api/sessions")

    assert response.status_code == 200
    assert response.json()["sessions"] == []


def test_invalid_otp_does_not_set_cookies() -> None:
    client = TestClient(app)
    pre_auth_token = _start_login(client)

    response = client.post(
        "/api/auth/otp",
        json={"pre_auth_token": pre_auth_token, "otp_code": "000000"},
    )

    assert response.status_code == 401
    assert pre_auth_token not in _pre_auth_sessions
    assert not client.cookies.get(AUTH_COOKIE)
    assert not client.cookies.get(AUTH_PRESENCE_COOKIE)


def test_expired_pre_auth_token_is_rejected() -> None:
    client = TestClient(app)
    pre_auth_token = _start_login(client)
    _pre_auth_sessions[pre_auth_token].expires_at = 0

    response = client.post(
        "/api/auth/otp",
        json={
            "pre_auth_token": pre_auth_token,
            "otp_code": get_settings().auth_otp_code,
        },
    )

    assert response.status_code == 401
    assert pre_auth_token not in _pre_auth_sessions
    assert not client.cookies.get(AUTH_COOKIE)


def test_bad_password_does_not_create_pre_auth_session() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/auth/ldap",
        json={"username": "admin", "password": "bad"},
    )

    assert response.status_code == 401
    assert _pre_auth_sessions == {}
    assert not client.cookies.get(AUTH_COOKIE)


def test_auth_me_returns_user_and_timeout_config() -> None:
    client = TestClient(app)

    _complete_login(client)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["user"]["username"] == "admin"
    assert body["idle_timeout_seconds"] == get_settings().auth_idle_timeout_seconds
    assert body["warn_before_seconds"] == get_settings().auth_warn_before_seconds


def test_touch_extends_idle_session() -> None:
    client = TestClient(app)
    token = _complete_login(client, username="123456", password="1234")

    session = _auth_sessions[token]
    session.last_activity -= get_settings().auth_idle_timeout_seconds - 5
    stale_activity = session.last_activity

    response = client.post("/api/auth/touch")

    assert response.status_code == 200
    assert response.json()["idle_timeout_seconds"] == get_settings().auth_idle_timeout_seconds
    assert _auth_sessions[token].last_activity > stale_activity


def test_idle_timeout_invalidates_session() -> None:
    client = TestClient(app)
    token = _complete_login(client, username="123456", password="1234")

    _auth_sessions[token].last_activity -= get_settings().auth_idle_timeout_seconds + 1

    response = client.get("/api/sessions")

    assert response.status_code == 401
    assert token not in _auth_sessions
