# Session Clock UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the API-configured idle timeout as a persistent bottom session clock and return users to login when idle time expires.

**Architecture:** Keep timeout values server-owned through `/api/auth/config`; the React guard consumes those values, tracks browser activity, refreshes server activity through `/api/auth/touch`, and logs out through `/api/auth/logout`. FastAPI middleware remains the server-side enforcement path for bypassed or stale clients.

**Tech Stack:** FastAPI, React, TypeScript, Vite, pytest, uv.

---

### Task 1: Reference And Current Behavior

**Files:**
- Inspect: `/Users/a453866/Python/analytics_agent/packages/ui/src/analytics_agent_ui/public/auth_redirect.js`
- Inspect: `pdftablesearch/auth.py`
- Inspect: `pdftablesearch/web_server.py`
- Inspect: `web/src/components/SessionTimeoutGuard.tsx`

- [x] Confirm current API exposes `idle_timeout_seconds`, `warn_before_seconds`, and `session_ttl_seconds`.
- [x] Confirm current middleware rejects idle sessions server-side.
- [x] Confirm current UI mounts `SessionTimeoutGuard` after login.

### Task 2: Improve Bottom Clock UI

**Files:**
- Modify: `web/src/components/SessionTimeoutGuard.tsx`

- [x] Make the bottom session badge explicit and accessible.
- [x] Show normal and warning states with stable dimensions.
- [x] Keep the modal action as "continue using" and force `/api/auth/touch`.

### Task 3: Add Frontend Regression Coverage

**Files:**
- Create or modify frontend tests if a test runner exists.
- Otherwise add backend tests only and verify TypeScript build.

- [x] Verify timeout config is typed and consumed.
- [x] Verify build catches UI/type regressions.

### Task 4: Verify End-To-End

**Commands:**
- `uv run qa test`
- `uv run --package pdf-intelligence-web ui-build`
- `uv run qa status`

- [x] Confirm Python auth tests pass.
- [x] Confirm Vite build succeeds.
- [x] Confirm services remain runnable on configured ports.
