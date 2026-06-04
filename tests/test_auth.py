from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from pdftablesearch.auth import LDAPUser, decode_pre_auth_jwt
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


def _patch_ldap(monkeypatch) -> None:
    monkeypatch.setattr(
        "pdftablesearch.web_server.ldap_client_from_settings",
        lambda: FakeLDAPClient(),
    )


def _patch_otp(monkeypatch, result: str = "0", calls: list[dict[str, str]] | None = None) -> None:
    async def fake_call_otp_subprocess(user_id: str, otp: str, client_ip_str: str) -> str:
        if calls is not None:
            calls.append({"user_id": user_id, "otp": otp, "client_ip": client_ip_str})
        return result

    monkeypatch.setattr("pdftablesearch.web_server.call_otp_subprocess", fake_call_otp_subprocess)


def _patch_sessions(monkeypatch, sessions: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = sessions if sessions is not None else {}

    async def fake_write_session(token: str, claims: dict[str, Any], ttl_seconds: int) -> bool:
        store[token] = {**claims, "_ttl": ttl_seconds}
        return True

    async def fake_read_session(token: str) -> dict[str, Any] | None:
        return store.get(token)

    async def fake_delete_session(token: str) -> None:
        store.pop(token, None)

    monkeypatch.setattr("pdftablesearch.web_server.write_session", fake_write_session)
    monkeypatch.setattr("pdftablesearch.web_server.read_session", fake_read_session)
    monkeypatch.setattr("pdftablesearch.web_server.delete_auth_session", fake_delete_session)
    monkeypatch.setattr("pdftablesearch.auth.read_session", fake_read_session)
    return store


def _start_ldap(client: TestClient, monkeypatch) -> str:
    _patch_ldap(monkeypatch)
    response = client.post(
        "/api/auth/ldap",
        json={"id": "admin", "password": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["pre_auth_token"], str)
    assert decode_pre_auth_jwt(body["pre_auth_token"])["username"] == "admin"
    assert set(body) == {"pre_auth_token"}
    assert "user" not in body
    assert "requires_otp" not in body
    assert not client.cookies.get(get_settings().auth_cookie_name)
    return body["pre_auth_token"]


def _complete_login(client: TestClient, monkeypatch, store: dict[str, dict[str, Any]] | None = None) -> str:
    _patch_otp(monkeypatch)
    sessions = _patch_sessions(monkeypatch, store)
    pre_auth_token = _start_ldap(client, monkeypatch)

    response = client.post(
        "/api/auth/otp",
        json={"pre_auth_token": pre_auth_token, "otp": "123456"},
    )

    assert response.status_code == 200
    assert response.json() == {"redirect": get_settings().auth_ui_url}
    token = client.cookies.get(get_settings().auth_cookie_name)
    assert token
    assert client.cookies.get("auth_presence") == "1"
    assert token in sessions
    assert sessions[token]["username"] == "admin"
    assert sessions[token]["jti"]
    return token


def test_auth_config_is_public() -> None:
    client = TestClient(app)

    response = client.get("/api/auth/config")

    assert response.status_code == 200
    body = response.json()
    assert body["idle_timeout_seconds"] == get_settings().auth_idle_timeout_dev_seconds
    assert body["warn_before_seconds"] == get_settings().auth_warn_before_seconds
    assert set(body) == {"idle_timeout_seconds", "warn_before_seconds"}


def test_ldap_returns_pre_auth_jwt_without_cookie(monkeypatch) -> None:
    client = TestClient(app)

    _start_ldap(client, monkeypatch)

    assert not client.cookies.get(get_settings().auth_cookie_name)


def test_internal_auth_routes_match_analytics_agent_paths(monkeypatch) -> None:
    client = TestClient(app)
    _patch_ldap(monkeypatch)
    _patch_otp(monkeypatch)
    _patch_sessions(monkeypatch)

    ldap_response = client.post(
        "/auth/ldap",
        json={"id": "admin", "password": "admin"},
    )
    assert ldap_response.status_code == 200

    otp_response = client.post(
        "/auth/otp",
        json={"pre_auth_token": ldap_response.json()["pre_auth_token"], "otp": "123456"},
    )
    assert otp_response.status_code == 200


def test_legacy_login_route_wraps_ldap_contract(monkeypatch) -> None:
    client = TestClient(app)
    _patch_ldap(monkeypatch)

    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )

    assert response.status_code == 200
    assert isinstance(response.json()["pre_auth_token"], str)
    assert "user" not in response.json()


def test_bad_password_does_not_create_pre_auth_token(monkeypatch) -> None:
    client = TestClient(app)
    _patch_ldap(monkeypatch)

    response = client.post(
        "/api/auth/ldap",
        json={"id": "admin", "password": "bad"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"
    assert not client.cookies.get(get_settings().auth_cookie_name)


def test_otp_calls_subprocess_writes_redis_and_allows_me(monkeypatch) -> None:
    client = TestClient(app)
    calls: list[dict[str, str]] = []
    _patch_otp(monkeypatch, calls=calls)
    _patch_sessions(monkeypatch)
    pre_auth_token = _start_ldap(client, monkeypatch)

    response = client.post(
        "/api/auth/otp",
        json={"pre_auth_token": pre_auth_token, "otp": "654321"},
        headers={"X-Forwarded-For": "10.10.10.10"},
    )

    assert response.status_code == 200
    assert calls == [{"user_id": "admin", "otp": "654321", "client_ip": "10.10.10.10"}]
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "admin"


def test_otp_failure_maps_to_401(monkeypatch) -> None:
    client = TestClient(app)
    _patch_otp(monkeypatch, result="6000")
    _patch_sessions(monkeypatch)
    pre_auth_token = _start_ldap(client, monkeypatch)

    response = client.post(
        "/api/auth/otp",
        json={"pre_auth_token": pre_auth_token, "otp": "000000"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "otp_failed"
    assert not client.cookies.get(get_settings().auth_cookie_name)


def test_otp_system_error_maps_to_500(monkeypatch) -> None:
    client = TestClient(app)
    _patch_otp(monkeypatch, result="error")
    _patch_sessions(monkeypatch)
    pre_auth_token = _start_ldap(client, monkeypatch)

    response = client.post(
        "/api/auth/otp",
        json={"pre_auth_token": pre_auth_token, "otp": "123456"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "otp_system_error"


def test_redis_write_failure_returns_503(monkeypatch) -> None:
    client = TestClient(app)
    _patch_otp(monkeypatch)
    pre_auth_token = _start_ldap(client, monkeypatch)

    async def fail_write_session(token: str, claims: dict[str, Any], ttl_seconds: int) -> bool:
        return False

    monkeypatch.setattr("pdftablesearch.web_server.write_session", fail_write_session)

    response = client.post(
        "/api/auth/otp",
        json={"pre_auth_token": pre_auth_token, "otp": "123456"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "session_store_unavailable"
    assert not client.cookies.get(get_settings().auth_cookie_name)


def test_expired_pre_auth_token_is_rejected(monkeypatch) -> None:
    client = TestClient(app)
    _patch_otp(monkeypatch)
    _patch_sessions(monkeypatch)

    response = client.post(
        "/api/auth/otp",
        json={"pre_auth_token": "not-a-valid-jwt", "otp": "123456"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "session_expired"


def test_valid_jwt_without_redis_session_is_rejected(monkeypatch) -> None:
    client = TestClient(app)
    sessions = _patch_sessions(monkeypatch)
    _complete_login(client, monkeypatch, sessions)
    sessions.clear()

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_verify_and_delete_session_use_bearer_token(monkeypatch) -> None:
    client = TestClient(app)
    sessions = _patch_sessions(monkeypatch)
    token = _complete_login(client, monkeypatch, sessions)

    verified = client.get("/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
    assert verified.status_code == 200
    assert verified.json()["username"] == "admin"

    deleted = client.delete("/api/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}

    rejected = client.get("/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
    assert rejected.status_code == 401


def test_logout_deletes_redis_session_and_both_cookies(monkeypatch) -> None:
    client = TestClient(app)
    sessions = _patch_sessions(monkeypatch)
    token = _complete_login(client, monkeypatch, sessions)

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert token not in sessions
    assert not client.cookies.get(get_settings().auth_cookie_name)
    assert not client.cookies.get("auth_presence")


def test_touch_requires_redis_backed_session(monkeypatch) -> None:
    client = TestClient(app)

    unauthenticated = client.post("/api/auth/touch")
    assert unauthenticated.status_code == 401

    _complete_login(client, monkeypatch)
    response = client.post("/api/auth/touch")

    assert response.status_code == 200
    assert response.json()["ok"] is True
