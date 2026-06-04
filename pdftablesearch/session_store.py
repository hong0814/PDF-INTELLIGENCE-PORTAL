"""Redis-backed authentication session store.

Session tokens are still signed JWTs, but a token is valid only while its
hashed key exists in Redis. This matches the analytics_agent auth model and
allows logout/session deletion to revoke otherwise unexpired JWTs.
"""

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
    """Return the Redis key for a session token."""
    return f"{_CACHE_KEY_PREFIX}{hashlib.sha256(token.encode()).hexdigest()}"


async def _get_redis():
    global _async_redis, _async_redis_initialized
    if _async_redis_initialized:
        return _async_redis
    _async_redis_initialized = True
    try:
        import redis.asyncio as aioredis

        _async_redis = aioredis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    except Exception:
        _async_redis = None
    return _async_redis


async def read_session(token: str) -> dict[str, Any] | None:
    """Return stored claims when the token is present in Redis."""
    r = await _get_redis()
    if r is None:
        return None
    try:
        value = await r.get(session_key(token))
    except Exception:
        return None
    return json.loads(value) if value is not None else None


async def write_session(token: str, claims: dict[str, Any], ttl_seconds: int) -> bool:
    """Persist claims using the same TTL as the issued JWT."""
    r = await _get_redis()
    if r is None:
        return False
    try:
        await r.setex(session_key(token), ttl_seconds, json.dumps(claims))
        return True
    except Exception:
        return False


async def delete_session(token: str) -> None:
    """Delete a session token from Redis on a best-effort basis."""
    r = await _get_redis()
    if r is None:
        return
    with contextlib.suppress(Exception):
        await r.delete(session_key(token))
