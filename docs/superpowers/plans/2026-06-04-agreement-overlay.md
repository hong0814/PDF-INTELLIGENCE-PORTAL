# Agreement Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate app entry after successful login with a PDF-specific data use agreement overlay, without changing the login screen UI.

**Architecture:** Keep `LoginScreen` unchanged. `App` stores successful auth in a pending state, shows a separate `AgreementOverlay`, and only commits authenticated app state after confirmation. Cancel logs out to remove cookies created by the login call.

**Tech Stack:** React, TypeScript, Tailwind CSS, FastAPI auth endpoints.

---

### Task 1: Reference Flow

**Files:**
- Inspect: `/Users/a453866/Python/analytics_agent/packages/ui/src/analytics_agent_ui/public/login.html`
- Inspect: `web/src/App.tsx`
- Inspect: `web/src/components/LoginScreen.tsx`

- [x] Confirm reference opens an agreement modal after successful auth and before app entry.
- [x] Confirm this repo can gate app entry in `App` without modifying `LoginScreen`.

### Task 2: Agreement Component

**Files:**
- Create: `web/src/components/AgreementOverlay.tsx`

- [x] Add scroll-safe agreement modal.
- [x] Include PDF extraction, table CSV download, translation, masking, and 7-day original PDF deletion terms.
- [x] Disable confirm until checkbox is checked.

### Task 3: Auth Flow Integration

**Files:**
- Modify: `web/src/App.tsx`

- [x] Store login result in `pendingAuthStatus`.
- [x] Show agreement over the unchanged login screen.
- [x] Confirm commits `authStatus` and enters the app.
- [x] Cancel calls logout and clears pending auth.

### Task 4: Verification

**Commands:**
- `uv run --package pdf-intelligence-web ui-build`
- `uv run pytest tests/test_auth.py -q`

- [x] Confirm TypeScript/Vite build succeeds.
- [x] Confirm auth tests still pass.
- [x] Capture login/agreement screen for visual check.
