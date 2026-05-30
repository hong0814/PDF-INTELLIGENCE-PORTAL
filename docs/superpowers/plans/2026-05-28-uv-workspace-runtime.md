# UV Workspace Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split local project management into explicit uv workspace packages for backend and web runtime commands while preserving root-level `uv run qa`, `uv run all`, `uv run api`, `uv run ui`, and Weaviate orchestration.

**Architecture:** Keep the current Python import package in `pdftablesearch/` to avoid a large source move. Make the repository root a thin workspace/orchestration package, make `pdftablesearch/` the backend workspace package through setuptools package-dir mapping, and make `web/` a tiny Python wrapper package that delegates to existing npm/Vite scripts.

**Tech Stack:** uv workspace, Python 3.12, setuptools for in-place backend packaging, hatchling for thin wrapper packages, FastAPI, React/Vite, embedded Weaviate, npm.

---

## Current Findings

- Root `pyproject.toml` currently owns the full backend dependency set and console scripts.
- `pdftablesearch/` is both the import package and the backend source directory.
- `web/` is already a separate npm/Vite project with `package.json` and `package-lock.json`.
- `db/weaviate` exists as the configured embedded Weaviate data path, but `.gitignore` ignores the whole directory so no placeholder can be tracked yet.
- `pdftablesearch/qa.py` and `pdftablesearch/port_utils.py` already provide a basic launcher, but service order and commands are implicit rather than modeled as a registry.

## Target Layout

```text
PDF-INTELLIGENCE-PORTAL/
├── pyproject.toml                 # uv workspace root and root command aliases
├── portal_workspace/              # tiny installable root package for root scripts
├── pdftablesearch/
│   ├── pyproject.toml             # backend package metadata and scripts
│   ├── __init__.py
│   ├── web_server.py
│   ├── port_utils.py
│   └── vectorstores/
├── web/
│   ├── pyproject.toml             # uv wrapper for npm/Vite commands
│   ├── pdf_intelligence_web/
│   │   └── cli.py
│   ├── package.json
│   └── src/
└── db/
    └── weaviate/
        └── .gitkeep               # tracks the intended data directory only
```

## Tasks

- [x] 1. Convert root `pyproject.toml` into a workspace root package named `pdf-intelligence-portal`.
  - Workspace members: `pdftablesearch`, `web`.
  - Workspace sources: `pdftablesearch = { workspace = true }`, `pdf-intelligence-web = { workspace = true }`.
  - Root scripts: `qa`, `all`, `killports`, `api`, `pdf-portal`, `weaviate`, `ui`, `ui-build`, `ui-preview`.

- [x] 2. Add `portal_workspace/__init__.py` so the root project is installable and root scripts are available through `uv run`.

- [x] 3. Add `pdftablesearch/pyproject.toml` with the backend dependency set and backend scripts.
  - Use setuptools with `package-dir = {"pdftablesearch" = "."}` to avoid moving source files.
  - Include packages: `pdftablesearch`, `pdftablesearch.loader`, `pdftablesearch.vectorstores`.

- [x] 4. Add `web/pyproject.toml` and `web/pdf_intelligence_web/cli.py`.
  - `uv run --package pdf-intelligence-web ui` delegates to `npm run dev`.
  - `ui-build`, `ui-preview`, and `ui-lint` delegate to npm scripts.
  - The wrapper installs npm dependencies if `web/node_modules` is missing.

- [x] 5. Refactor service launch configuration.
  - Add an explicit service order and command registry to `pdftablesearch/port_utils.py`.
  - Start services with workspace-aware commands:
    - Weaviate: `uv run --package pdftablesearch weaviate`
    - Hybrid: `uv run --package pdftablesearch opendataloader-pdf-hybrid --port <port>`
    - API: `uv run --package pdftablesearch api start ...`
    - UI: `uv run --package pdf-intelligence-web ui -- --host 127.0.0.1 --port <port>`
  - Preserve `uv run all`, `uv run killports`, and `uv run qa`.

- [x] 6. Expand `pdftablesearch/qa.py` into an analytics_agent-style local menu.
  - Show service statuses before each prompt.
  - Menu entries: E2E QA, Manual, Tests, Logs, Kill Ports, Exit.
  - Provide command subcommands for `status`, `start`, `stop`, `restart`, `logs`, `test`.
  - Keep non-TTY behavior as status-only.

- [x] 7. Track only the intended Weaviate directory.
  - Change `.gitignore` from ignoring `db/weaviate/` wholesale to ignoring `db/weaviate/*` while allowing `db/weaviate/.gitkeep`.
  - Add `db/weaviate/.gitkeep`.

- [x] 8. Update README and scripts.
  - Document `uv sync --all-packages --extra dev`.
  - Document root commands and package-specific commands.
  - Update project structure to mention root workspace, backend package, web wrapper, and `db/weaviate`.
  - Update `scripts/setup.sh` and `scripts/start.sh` to use workspace-aware commands.

- [x] 9. Verify the workspace.
  - `uv lock`
  - `uv run qa status`
  - `uv run --package pdftablesearch qa status`
  - `uv run --package pdf-intelligence-web ui-build`
  - `uv run --extra dev pytest tests/test_vectorstore.py tests/test_core.py tests/test_models.py tests/test_vectorstore_contract.py tests/test_weaviate_store.py tests/test_weaviate_integration.py`

## Verification Log

```text
uv lock
Resolved 234 packages

uv run qa status
ok

uv run --package pdftablesearch qa status
ok

uv run qa commands
ok

uv run --package pdf-intelligence-web ui-build
vite build succeeded

uv run qa test
45 passed

uv run qa test --weaviate
1 passed

PDF_PORTAL_PORT=18010 PDF_PORTAL_UI_PORT=15173 PDF_PORTAL_HYBRID_PORT=15002 WEAVIATE_PORT=18051 WEAVIATE_GRPC_PORT=18052 WEAVIATE_DATA_DIR=<tmp> uv run all
weaviate ready
hybrid ready
api ready
ui ready
```
