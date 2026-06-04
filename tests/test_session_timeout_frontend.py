from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_idle_timeout_redirects_browser_to_get_logout() -> None:
    guard = (ROOT / "web/src/components/SessionTimeoutGuard.tsx").read_text(encoding="utf-8")
    client = (ROOT / "web/src/api/client.ts").read_text(encoding="utf-8")

    assert "export function logoutUrl()" in client
    assert "window.location.replace(api.logoutUrl())" in guard
    assert "await api.logout()" not in guard
