# Auth Technical Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PDF Intelligence Portal authentication technically match `~/Python/analytics_agent` for LDAP, OTP, Redis-backed session validation, cookies, and idle config while keeping the React UI and omitting Chainlit-only `/ui-auth`.

**Architecture:** Replace in-memory pre-auth and JWT-only sessions with signed pre-auth JWTs, Java OTP subprocess validation, and Redis-backed session persistence. Keep same-origin React API calls under `/api/auth/*`; expose compatibility route names and request shapes matching analytics_agent where possible.

**Tech Stack:** FastAPI, PyJWT, ldap3, redis.asyncio, React/Vite, pytest.

---

### Task 1: Redis Session Store

**Files:**
- Create: `pdftablesearch/session_store.py`
- Modify: `pyproject.toml`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Add Redis dependency**

Add `redis>=5.0` to the root `pyproject.toml` dependencies.

- [ ] **Step 2: Implement session store**

Create `pdftablesearch/session_store.py` with:

```python
from __future__ import annotations

import contextlib
import hashlib
import json
from typing import Any

from pdftablesearch.config import get_settings

_CACHE_KEY_PREFIX = "auth_verify:"
_async_redis = None
_async_redis_initialized = False


def session_key(token: str) -> str:
    return f"{_CACHE_KEY_PREFIX}{hashlib.sha256(token.encode()).hexdigest()}"


async def _get_redis():
    global _async_redis, _async_redis_initialized
    if _async_redis_initialized:
        return _async_redis
    _async_redis_initialized = True
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        _async_redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    except Exception:
        _async_redis = None
    return _async_redis


async def read_session(token: str) -> dict[str, Any] | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        value = await r.get(session_key(token))
    except Exception:
        return None
    return json.loads(value) if value is not None else None


async def write_session(token: str, claims: dict[str, Any], ttl_seconds: int) -> bool:
    r = await _get_redis()
    if r is None:
        return False
    try:
        await r.setex(session_key(token), ttl_seconds, json.dumps(claims))
        return True
    except Exception:
        return False


async def delete_session(token: str) -> None:
    r = await _get_redis()
    if r is None:
        return
    with contextlib.suppress(Exception):
        await r.delete(session_key(token))
```

- [ ] **Step 3: Verify import**

Run: `uv run python -c "import pdftablesearch.session_store as s; print(s.session_key('x'))"`

Expected: prints a key beginning with `auth_verify:`.

### Task 2: JWT and OTP Parity

**Files:**
- Modify: `pdftablesearch/config.py`
- Modify: `pdftablesearch/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Add settings**

Add settings for Redis URL, OTP JAR, OTP SDK JAR, OTP company codes, OTP ASSTSQ, and dev/prod idle timeout variants.

- [ ] **Step 2: Replace in-memory pre-auth**

Replace `_pre_auth_sessions` with `issue_pre_auth_jwt()` and `decode_pre_auth_jwt()` using `sub="pre_auth"`, `jti`, `iat`, and `exp`.

- [ ] **Step 3: Add OTP subprocess**

Add `call_otp_subprocess(user_id, otp, client_ip_str)` matching analytics_agent behavior:
- return `"0"` for success
- return `"6000"` for failed OTP
- return `"error"` for timeout, missing JAR, non-zero exit, or process exception

- [ ] **Step 4: Add session JWT**

Add `issue_session_jwt(user_data)` returning `(token, ttl_seconds, jti)` and set `sub="session"`.

### Task 3: API Contract Parity

**Files:**
- Modify: `pdftablesearch/web_server.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Rename request models**

Use request shapes matching analytics_agent:

```python
class LDAPAuthRequest(BaseModel):
    id: str
    password: str


class OTPAuthRequest(BaseModel):
    pre_auth_token: str
    otp: str
```

- [ ] **Step 2: Add `/api/auth/ldap`**

Implement `POST /api/auth/ldap` to validate LDAP and return `{"pre_auth_token": token, **auth_config()}` without setting cookies.

- [ ] **Step 3: Keep compatibility `/api/auth/login`**

Keep `/api/auth/login` as a wrapper for existing React compatibility only if needed, but React should use `/api/auth/ldap`.

- [ ] **Step 4: Update `/api/auth/otp`**

Decode pre-auth JWT, call OTP subprocess, write session claims to Redis, return 503 on unavailable Redis, set both `auth_token` and `auth_presence` cookies on success.

- [ ] **Step 5: Update `/api/auth/me` and `/api/auth/touch`**

Require the cookie token to exist in Redis before returning the current user.

- [ ] **Step 6: Update logout**

Delete Redis session and clear both cookies.

### Task 4: React Contract Alignment

**Files:**
- Modify: `web/src/api/client.ts`
- Modify: `web/src/types/index.ts`
- Modify: `web/src/App.tsx`

- [ ] **Step 1: LDAP endpoint**

Change login API call to `POST /api/auth/ldap` with `{id, password}`.

- [ ] **Step 2: OTP field**

Change OTP API call body from `{otp_code}` to `{otp}`.

- [ ] **Step 3: Preserve agreement flow**

Keep OTP success followed by `AgreementOverlay`, but do not add `/ui-auth` because this app is React and does not need Chainlit `access_token`.

### Task 5: Tests and Verification

**Files:**
- Modify: `tests/test_auth.py`

- [ ] **Step 1: Mock OTP subprocess**

Patch `pdftablesearch.web_server.call_otp_subprocess` to return `"0"` for success and `"6000"` for OTP failure.

- [ ] **Step 2: Mock Redis store**

Patch `pdftablesearch.web_server.write_session`, `read_session`, and `delete_session` in tests so auth tests do not require a live Redis process.

- [ ] **Step 3: Run focused tests**

Run: `uv run pytest tests/test_auth.py tests/test_ldap_server.py -q`

Expected: all tests pass.

- [ ] **Step 4: Run frontend build**

Run: `cd web && npm run build`

Expected: TypeScript and Vite build pass.
