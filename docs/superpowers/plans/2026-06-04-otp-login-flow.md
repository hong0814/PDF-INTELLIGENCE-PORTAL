# OTP Login Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an OTP step between LDAP-compatible credential validation and the existing PDF service agreement gate.

**Architecture:** `/api/auth/ldap` validates ID/PW and returns a short-lived `pre_auth_token` without cookies. `/api/auth/otp` validates that token and OTP code, then creates the normal httpOnly auth cookies. React keeps the main-branch login card intact, opens an OTP modal after LDAP success, and only calls `onLogin` after OTP succeeds so the existing agreement overlay remains the final gate.

**Tech Stack:** FastAPI, in-memory auth sessions, Pydantic settings, React, TypeScript, Tailwind CSS, pytest, Vite.

---

### Task 1: Backend Pre-Auth Session

**Files:**
- Modify: `pdftablesearch/config.py`
- Modify: `pdftablesearch/auth.py`
- Modify: `pdftablesearch/web_server.py`

- [x] Add `AUTH_PRE_AUTH_TTL_SECONDS` and `AUTH_OTP_CODE` settings.
- [x] Add short-lived pre-auth session storage.
- [x] Change `/api/auth/ldap` to return `pre_auth_token` and not set auth cookies.
- [x] Add `/api/auth/otp` to validate OTP and set normal auth cookies.

### Task 2: Frontend OTP Modal

**Files:**
- Modify: `web/src/types/index.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/components/LoginScreen.tsx`

- [x] Add `PreAuthStatus` type.
- [x] Change LDAP client call to return pre-auth status.
- [x] Add OTP verify client call.
- [x] Keep the main login card visually aligned with `origin/main`.
- [x] Open OTP as a modal after LDAP success.
- [x] Call `onLogin` only after OTP succeeds.

### Task 3: Tests And Docs

**Files:**
- Modify: `tests/test_auth.py`
- Modify: `.env.example`
- Modify: `README.md`

- [x] Update auth tests for `LDAP -> OTP -> cookie` flow.
- [x] Cover invalid and expired OTP sessions.
- [x] Document dev OTP settings and login order.

### Task 4: Verification

**Commands:**
- `uv run pytest tests/test_auth.py -q`
- `uv run --package pdf-intelligence-web ui-build`
- `uv run qa test`

- [x] Confirm auth tests pass.
- [x] Confirm TypeScript/Vite build passes.
- [x] Confirm full QA test command passes.
