from fastapi.testclient import TestClient

from pdftablesearch.auth import LDAPUser, _pre_auth_sessions
from pdftablesearch.config import get_settings
from pdftablesearch.web_server import app


class FakeLDAPClient:
    def authenticate(self, username: str, password: str) -> LDAPUser | None:
        if username == "admin" and password == "admin":
            return LDAPUser(
                user_id="admin",
                username="admin",
                name="Administrator",
                email="admin@example.test",
                department="IT",
                roles=["admin"],
            )
        return None


def setup_function() -> None:
    _pre_auth_sessions.clear()


def teardown_function() -> None:
    _pre_auth_sessions.clear()


def _patch_ldap(monkeypatch) -> None:
    monkeypatch.setattr(
        "pdftablesearch.web_server.ldap_client_from_settings",
        lambda: FakeLDAPClient(),
    )


def _start_login(client: TestClient, monkeypatch) -> str:
    _patch_ldap(monkeypatch)
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requires_otp"] is True
    assert body["user"]["username"] == "admin"
    assert body["pre_auth_ttl_seconds"] == get_settings().auth_pre_auth_ttl_seconds
    assert not client.cookies.get(get_settings().auth_cookie_name)
    return body["pre_auth_token"]


def _complete_login(client: TestClient, monkeypatch) -> str:
    pre_auth_token = _start_login(client, monkeypatch)
    response = client.post(
        "/api/auth/otp",
        json={
            "pre_auth_token": pre_auth_token,
            "otp_code": get_settings().auth_otp_code,
        },
    )
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "admin"
    assert pre_auth_token not in _pre_auth_sessions
    token = client.cookies.get(get_settings().auth_cookie_name)
    assert token
    return token


def test_auth_config_is_public() -> None:
    client = TestClient(app)

    response = client.get("/api/auth/config")

    assert response.status_code == 200
    body = response.json()
    assert body["idle_timeout_seconds"] == get_settings().auth_idle_timeout_seconds
    assert body["warn_before_seconds"] == get_settings().auth_warn_before_seconds
    assert body["pre_auth_ttl_seconds"] == get_settings().auth_pre_auth_ttl_seconds


def test_login_returns_pre_auth_token_without_cookie(monkeypatch) -> None:
    client = TestClient(app)

    pre_auth_token = _start_login(client, monkeypatch)

    assert pre_auth_token in _pre_auth_sessions
    assert not client.cookies.get(get_settings().auth_cookie_name)


def test_bad_password_does_not_create_pre_auth_session(monkeypatch) -> None:
    client = TestClient(app)
    _patch_ldap(monkeypatch)

    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "bad"},
    )

    assert response.status_code == 401
    assert _pre_auth_sessions == {}
    assert not client.cookies.get(get_settings().auth_cookie_name)


def test_otp_sets_auth_cookie_and_allows_me(monkeypatch) -> None:
    client = TestClient(app)

    _complete_login(client, monkeypatch)
    response = client.get("/api/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "admin"
    assert body["idle_timeout_seconds"] == get_settings().auth_idle_timeout_seconds


def test_invalid_otp_consumes_pre_auth_token(monkeypatch) -> None:
    client = TestClient(app)
    pre_auth_token = _start_login(client, monkeypatch)

    response = client.post(
        "/api/auth/otp",
        json={"pre_auth_token": pre_auth_token, "otp_code": "000000"},
    )

    assert response.status_code == 401
    assert pre_auth_token not in _pre_auth_sessions
    assert not client.cookies.get(get_settings().auth_cookie_name)


def test_expired_pre_auth_token_is_rejected(monkeypatch) -> None:
    client = TestClient(app)
    pre_auth_token = _start_login(client, monkeypatch)
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
    assert not client.cookies.get(get_settings().auth_cookie_name)


def test_touch_requires_and_accepts_authenticated_session(monkeypatch) -> None:
    client = TestClient(app)

    unauthenticated = client.post("/api/auth/touch")
    assert unauthenticated.status_code == 401

    _complete_login(client, monkeypatch)
    response = client.post("/api/auth/touch")

    assert response.status_code == 200
    assert response.json()["ok"] is True
