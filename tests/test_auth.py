from fastapi.testclient import TestClient

from pdftablesearch.auth import AUTH_COOKIE, AUTH_PRESENCE_COOKIE, _auth_sessions
from pdftablesearch.config import get_settings
from pdftablesearch.web_server import app


def setup_function() -> None:
    _auth_sessions.clear()


def teardown_function() -> None:
    _auth_sessions.clear()


def test_auth_config_is_public() -> None:
    client = TestClient(app)

    response = client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json()["idle_timeout_seconds"] == get_settings().auth_idle_timeout_seconds


def test_api_requires_login() -> None:
    client = TestClient(app)

    response = client.get("/api/sessions")

    assert response.status_code == 401


def test_dev_login_sets_cookies_and_allows_api() -> None:
    client = TestClient(app)

    login = client.post(
        "/api/auth/ldap",
        json={"username": "admin", "password": "admin"},
    )
    assert login.status_code == 200
    assert client.cookies.get(AUTH_COOKIE)
    assert client.cookies.get(AUTH_PRESENCE_COOKIE) == "1"

    response = client.get("/api/sessions")

    assert response.status_code == 200
    assert response.json()["sessions"] == []


def test_auth_me_returns_user_and_timeout_config() -> None:
    client = TestClient(app)

    login = client.post(
        "/api/auth/ldap",
        json={"username": "admin", "password": "admin"},
    )
    assert login.status_code == 200

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["user"]["username"] == "admin"
    assert body["idle_timeout_seconds"] == get_settings().auth_idle_timeout_seconds
    assert body["warn_before_seconds"] == get_settings().auth_warn_before_seconds


def test_touch_extends_idle_session() -> None:
    client = TestClient(app)
    login = client.post(
        "/api/auth/ldap",
        json={"username": "123456", "password": "1234"},
    )
    assert login.status_code == 200

    token = client.cookies.get(AUTH_COOKIE)
    assert token
    session = _auth_sessions[token]
    session.last_activity -= get_settings().auth_idle_timeout_seconds - 5
    stale_activity = session.last_activity

    response = client.post("/api/auth/touch")

    assert response.status_code == 200
    assert response.json()["idle_timeout_seconds"] == get_settings().auth_idle_timeout_seconds
    assert _auth_sessions[token].last_activity > stale_activity


def test_idle_timeout_invalidates_session() -> None:
    client = TestClient(app)
    login = client.post(
        "/api/auth/ldap",
        json={"username": "123456", "password": "1234"},
    )
    assert login.status_code == 200

    token = client.cookies.get(AUTH_COOKIE)
    assert token
    _auth_sessions[token].last_activity -= get_settings().auth_idle_timeout_seconds + 1

    response = client.get("/api/sessions")

    assert response.status_code == 401
    assert token not in _auth_sessions
