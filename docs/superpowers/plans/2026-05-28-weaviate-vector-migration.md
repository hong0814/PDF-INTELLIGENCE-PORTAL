# Weaviate Vector Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move PDF Intelligence Portal from Chroma-backed vector search to a Weaviate-backed vector store while preserving the current `TableVectorStore` API, adding `uv run qa` service orchestration, and preparing the repository for package-level ownership through uv workspace packages.

**Architecture:** Keep the current user-facing API stable first. Introduce a backend-agnostic vector store layer, implement Weaviate as a compatible adapter, route existing table and document-chunk search through the adapter, then split service ownership into `core`, `api`, `worker`, and `ui` packages once the storage boundary is clean.

**Tech Stack:** Python 3.12, uv workspace, FastAPI, React/Vite, LangChain `Document`, local `SentenceTransformerEmbeddings`, Weaviate Python client v4, embedded Weaviate for local dev, Chroma as temporary fallback during migration, pytest.

---

## Current Findings

- Current branch is `feature/weaviate`.
- Existing Chroma surface is concentrated in `pdftablesearch/vectorstore.py`, with direct callers in `pdftablesearch/core.py`, `pdftablesearch/search.py`, `pdftablesearch/hybrid_search.py`, `pdftablesearch/web_server.py`, `streamlit_app.py`, and `examples/langchain_demo.py`.
- `TableVectorStore` must initially keep this public contract:
  - `get_or_create(...)`
  - `vectorstore`
  - `is_initialized`
  - `add_documents(documents, skip_existing=True) -> list[str]`
  - `similarity_search(query, k=5, filter_metadata=None) -> list[tuple[Document, float]]`
  - `get_document_count()`
  - `get_stats()`
  - `reset()`
- Search callers currently assume Chroma distance semantics: lower score is better.
- `pdftablesearch/search.py` reaches into Chroma private internals via `vector_store.vectorstore._collection.get(...)`; replace this before backend switching.
- `pdftablesearch/web_server.py` uses two logical vector collections:
  - table documents, usually collection `pdf_tables`
  - text chunks, currently dynamic collection `doc_chunks_{session_id}`
- Session lifecycle currently maps Chroma persistence to temp directories such as `pdf_chroma_*` and `pdf_docchunks_*`. Weaviate should use a stable data directory plus `session_id` filtering or tenants, not one class per temp directory.
- Current UI is React/Vite under `web/`, while Python is still one root package.
- `web/vite.config.ts` proxies `/api` to `8000`, but the new local runner defaults to `8111`; this should be normalized during service orchestration.

## External References Checked

- Weaviate Python client v4 docs: `https://docs.weaviate.io/weaviate/client-libraries/python`
- Weaviate embedded connection docs: `https://docs.weaviate.io/weaviate/connections/connect-embedded`
- Weaviate bring-your-own-vectors docs: `https://docs.weaviate.io/weaviate/starter-guides/custom-vectors`
- Weaviate vector similarity docs: `https://docs.weaviate.io/weaviate/search/similarity`
- Weaviate hybrid search docs: `https://docs.weaviate.io/weaviate/search/hybrid`
- Weaviate filters docs: `https://docs.weaviate.io/weaviate/search/filters`
- uv workspace docs: `https://docs.astral.sh/uv/concepts/projects/workspaces/`
- uv run docs: `https://docs.astral.sh/uv/concepts/projects/run/`

Important current-doc decision: use Weaviate Python v4 `Configure.Vectors.self_provided()` / `vector_config`, not the older `Configure.Vectorizer.none()` API where possible.

## Target Runtime Shape

```text
uv run qa
  -> status/start/stop/logs menu
  -> manages API, UI dev server or static build, hybrid PDF server, Weaviate

uv run all
  -> starts all local services in one non-interactive command

uv run killports
  -> stops API/UI/hybrid/Weaviate HTTP/Weaviate gRPC ports

uv run weaviate
  -> starts embedded Weaviate with persistent data under db/weaviate

uv run pdf-portal
  -> starts FastAPI portal
```

Default local ports should be explicit and configurable:

```text
API:              8111
UI dev server:    8110
Hybrid PDF:       8112
Weaviate HTTP:    8113
Weaviate gRPC:    8114
```

Use `8113/8114` instead of analytics_agent's `50051/50052` to avoid collisions if both repositories are being run on the same machine.

## Target Vector Data Model

Use two durable Weaviate collections, not one class per session:

```text
PdfTable
  doc_hash              text, filterable
  session_id            text, filterable
  collection_name       text, filterable
  document_name         text, filterable
  table_id              text, filterable
  page_number           int, filterable
  page_content          text, searchable
  metadata_json         text, not searchable

PdfChunk
  doc_hash              text, filterable
  session_id            text, filterable
  collection_name       text, filterable
  source_pdf            text, filterable
  chunk_index           int, filterable
  page_number           int, filterable
  page_content          text, searchable
  metadata_json         text, not searchable
```

Store the vector as Weaviate's object vector, not as a property. Serialize rich metadata such as `bounding_box`, `table_html`, `table_context`, and `merged_table_html` into `metadata_json`, then hydrate back into `langchain_core.documents.Document`.

## Implementation Tasks

- [x] 1. Snapshot current dirty state with `git status --short --branch` and identify changes already present before this migration. Do not revert unrelated edits.
- [x] 2. Add a compatibility note to the implementation branch description or commit message: Chroma remains available behind a feature flag until parity is verified.
- [x] 3. Expand `pdftablesearch/config.py` with vector backend settings:
  - `vector_backend: str = "chroma"`
  - `weaviate_host: str = "127.0.0.1"`
  - `weaviate_port: int = 8113`
  - `weaviate_grpc_port: int = 8114`
  - `weaviate_use_embedded: bool = True`
  - `weaviate_data_dir: str = "./db/weaviate"`
  - `weaviate_table_collection: str = "PdfTable"`
  - `weaviate_chunk_collection: str = "PdfChunk"`
  - `weaviate_hybrid_alpha: float = 0.6`
- [x] 4. Add `weaviate-client>=4.16.4` to `pyproject.toml` first, because current Weaviate docs note vector configuration API changes around v4.16.
- [x] 5. Create `pdftablesearch/vectorstores/base.py` with a protocol or abstract base for the shared vector store operations currently exposed by `TableVectorStore`.
- [x] 6. Move the existing Chroma implementation from `pdftablesearch/vectorstore.py` into `pdftablesearch/vectorstores/chroma_store.py` with behavior unchanged.
- [x] 7. Keep `pdftablesearch/vectorstore.py` as the compatibility facade that returns a backend implementation based on `VECTOR_BACKEND` / `Settings.vector_backend`.
- [x] 8. Add wrapper methods to the facade before touching Weaviate:
  - `list_documents(limit: int | None = None) -> list[Document]`
  - `delete_where(filter_metadata: dict[str, Any]) -> int`
  - `clear_collection() -> None`
- [x] 9. Replace `pdftablesearch/search.py:list_stored_tables()` private Chroma access with `TableVectorStore.list_documents()`.
- [x] 10. Replace any remaining direct `_collection` access in project code with public wrapper methods.
- [x] 11. Add focused tests in `tests/test_vectorstore_contract.py` for the backend-neutral contract:
  - uninitialized search raises `VectorSearchError`
  - `add_documents` returns IDs
  - `similarity_search` returns `(Document, float)`
  - lower score remains better
  - metadata filters preserve exact-match behavior
  - `list_documents` hydrates metadata and page content
  - `reset` removes indexed documents for that logical collection
- [x] 12. Implement `pdftablesearch/vectorstores/weaviate_client.py` with:
  - cached `get_weaviate_client()`
  - local connection via `weaviate.connect_to_local(...)`
  - external connection via `weaviate.connect_to_custom(...)`
  - optional API key support via `WEAVIATE_API_KEY`
  - `close_weaviate_client()` for tests and shutdown
- [x] 13. Implement `pdftablesearch/vectorstores/weaviate_server.py` with a `main()` entry point for `uv run weaviate`, using embedded Weaviate and blocking until interrupted.
- [x] 14. Configure embedded Weaviate with `hostname`, `port`, `grpc_port`, `persistence_data_path`, `PORT`, `GRPC_PORT`, `CLUSTER_IN_LOCAL=true`, and a deterministic `CLUSTER_HOSTNAME`.
- [x] 15. Implement collection bootstrapping in `pdftablesearch/vectorstores/weaviate_schema.py` using `Configure.Vectors.self_provided()` and explicit properties for `PdfTable` and `PdfChunk`.
- [x] 16. Implement deterministic UUID generation from `collection_name`, `session_id`, document hash, and object type so repeated indexing is idempotent.
- [x] 17. Implement metadata normalization:
  - simple scalar metadata becomes typed Weaviate properties where useful
  - all original metadata is preserved in `metadata_json`
  - `bounding_box` and nested table fields survive round trip exactly
- [x] 18. Implement `pdftablesearch/vectorstores/weaviate_store.py` with the same constructor shape as `TableVectorStore(embeddings, persist_dir, collection_name)`.
- [x] 19. Map `persist_dir` compatibility to a logical `session_id`:
  - for current API sessions, derive `session_id` from the existing session id where available
  - for legacy CLI/temp dir flows, derive a stable hash from `persist_dir`
  - keep `persist_dir` in `get_stats()` for compatibility
- [x] 20. Implement `add_documents()` for Weaviate:
  - call local embedding function once per document
  - insert objects with self-provided vectors
  - skip existing by deterministic UUID when `skip_existing=True`
  - return inserted or existing IDs consistently with the Chroma facade contract
- [x] 21. Implement `similarity_search()` for Weaviate using `near_vector` with the same embedding model used at ingest.
- [x] 22. Normalize Weaviate distance metadata so the returned score keeps current semantics: lower is better.
- [x] 23. Implement exact metadata filters by translating `filter_metadata` to `weaviate.classes.query.Filter.by_property(...).equal(...)`.
- [x] 24. Add optional hybrid search support for Weaviate table and chunk collections using BM25 over `page_content` plus vector search, controlled by `weaviate_hybrid_alpha`.
- [x] 25. Keep the initial default backend as Chroma until contract tests pass for both backends.
- [x] 26. Add unit tests with a fake Weaviate collection/client so vector store behavior can be verified without starting an embedded server.
- [x] 27. Add an integration test marker such as `@pytest.mark.weaviate` that starts or expects local Weaviate and verifies:
  - collection creation
  - insert
  - search
  - metadata filter
  - reset/delete
  - re-open persistence
- [x] 28. Update `pdftablesearch/web_server.py` session creation so each session stores a stable `session_id` and does not depend on deleting a Weaviate data directory for cleanup.
- [x] 29. Replace session cleanup for Weaviate with `delete_where({"session_id": session_id})`, while keeping `shutil.rmtree(chroma_dir)` for Chroma fallback.
- [x] 30. Verify document QA fusion still works because `Document.page_content` must round trip exactly for BM25/vector matching in `pdftablesearch/web_server.py`.
- [x] 31. Add `pdftablesearch/port_utils.py` based on the analytics_agent pattern:
  - `_pids_on_port`
  - `_is_alive`
  - `kill_port`
  - `killports`
  - `run_weaviate`
  - `run_api`
  - `run_ui`
  - `run_all`
- [x] 32. Add `pdftablesearch/qa.py` with `uv run qa` support:
  - status
  - start all
  - stop all
  - restart all
  - logs directory under `logs/qa_<timestamp>/`
  - readiness check for Weaviate `/v1/.well-known/ready`
- [x] 33. Add root scripts in `pyproject.toml`:
  - `qa = "pdftablesearch.qa:main"`
  - `all = "pdftablesearch.port_utils:run_all"`
  - `killports = "pdftablesearch.port_utils:killports"`
  - `weaviate = "pdftablesearch.vectorstores.weaviate_server:main"`
  - `pdf-portal = "pdftablesearch.run:main"`
- [x] 34. Normalize API/UI port settings:
  - update `web/vite.config.ts` proxy to match configured API port or read from `VITE_API_BASE_URL`
  - expose `PDF_PORTAL_PORT=8111`
  - expose `PDF_PORTAL_UI_PORT=8110`
- [x] 35. Update `.env.example` with Chroma fallback and Weaviate settings.
- [x] 36. Update README setup commands:
  - `uv sync`
  - `uv run qa`
  - `uv run weaviate`
  - `VECTOR_BACKEND=weaviate uv run pdf-portal`
  - `uv run killports`
- [x] 37. Run Chroma regression tests first:
  - `uv run pytest tests/test_vectorstore.py tests/test_core.py tests/test_models.py`
- [x] 38. Run Weaviate contract tests with fake client:
  - `VECTOR_BACKEND=weaviate uv run pytest tests/test_vectorstore_contract.py`
- [x] 39. Run local Weaviate smoke:
  - `uv run killports`
  - `uv run weaviate`
  - `curl http://127.0.0.1:8113/v1/.well-known/ready`
  - `VECTOR_BACKEND=weaviate uv run pytest -m weaviate`
- [ ] 40. Run application smoke with Weaviate:
  - `VECTOR_BACKEND=weaviate uv run pdf-portal start --with-hybrid`
  - upload a small PDF
  - table search
  - smart search
  - document QA
  - session cleanup
- [ ] 41. Only after Weaviate parity, flip default `vector_backend` from `chroma` to `weaviate`.
- [ ] 42. Keep Chroma adapter for one release cycle or until all tests and manual workflows prove Weaviate parity.

## Package Split Tasks

Do not do these before the vector store facade exists. The facade is what prevents package splitting from becoming a tangled import rewrite.

- [ ] 43. Convert root `pyproject.toml` to a uv workspace root with members:
  - `packages/core`
  - `packages/api`
  - `packages/worker`
- [ ] 44. Add `[tool.uv.sources]` for workspace-local packages.
- [ ] 45. Move reusable package code into `packages/core/src/pdftablesearch/` while preserving the public import name `pdftablesearch`.
- [ ] 46. Move FastAPI runner code from `pdftablesearch/web_server.py` and `pdftablesearch/run.py` into `packages/api/src/pdf_intelligence_api/`, with temporary import shims left behind if needed.
- [ ] 47. Extract worker-like functions from `pdftablesearch/web_server.py` into `packages/worker/src/pdf_intelligence_worker/` only after their inputs/outputs are explicit.
- [ ] 48. Keep `web/` as the Node/Vite package; optionally add a small Python `packages/ui` only if `uv run ui` must manage `npm run dev` or static build serving.
- [ ] 49. Update tests to import workspace packages through uv and keep root test paths initially.
- [ ] 50. Run workspace verification:
  - `uv lock`
  - `uv sync --all-packages`
  - `uv run --package pdftablesearch pytest`
  - `uv run qa`

## Subagent Work Allocation

- Vector-store worker: implement tasks 3-27 and own all tests under `tests/test_vectorstore_contract.py`.
- Runtime worker: implement tasks 31-40 and own `uv run qa`, `uv run all`, `uv run killports`, and local smoke scripts.
- Package-layout worker: implement tasks 43-50 only after vector-store tests pass.
- Reviewer worker: independently inspect `pdftablesearch/web_server.py`, `pdftablesearch/search.py`, and `pdftablesearch/vectorstores/` for Chroma leaks, score-direction regressions, and session cleanup mistakes.

## Execution Log

Task 1 snapshot before migration implementation:

```text
## feature/weaviate
 M pdftablesearch/local_embeddings.py
 M pdftablesearch/web_server.py
 M pyproject.toml
 M web/package-lock.json
?? .python-version
?? docs/superpowers/
?? pdftablesearch/run.py
?? scripts/
```

Task 2 compatibility note: Chroma remains the default vector backend until Weaviate contract tests, local Weaviate smoke tests, and application smoke tests all pass. The implementation uses a backend flag so `VECTOR_BACKEND=chroma` can be used as a rollback path during migration.

First implementation verification:

```text
uv run --extra dev pytest tests/test_vectorstore.py tests/test_vectorstore_contract.py tests/test_weaviate_store.py

13 passed in 4.46s

uv run qa status

api            :8111  pid=40244        ready
ui             :8110  pid=-            not-ready
hybrid         :8112  pid=1265         ready
weaviate       :8113 pid=-            not-ready
weaviate_grpc  :8114 pid=-            not-ready

uv run --extra dev pytest tests/test_vectorstore.py tests/test_vectorstore_contract.py tests/test_weaviate_store.py

13 passed in 3.87s

uv run python -m py_compile pdftablesearch/web_server.py pdftablesearch/port_utils.py pdftablesearch/qa.py pdftablesearch/vectorstore.py pdftablesearch/vectorstores/*.py

ok

uv run --extra dev pytest tests/test_vectorstore.py tests/test_vectorstore_contract.py tests/test_weaviate_store.py

13 passed in 3.55s

uv run --extra dev pytest tests/test_vectorstore.py tests/test_core.py tests/test_models.py

37 passed in 3.02s

VECTOR_BACKEND=weaviate uv run --extra dev pytest tests/test_vectorstore_contract.py tests/test_weaviate_store.py tests/test_weaviate_integration.py

6 passed, 1 skipped in 3.61s

uv run weaviate
curl http://127.0.0.1:8113/v1/.well-known/ready
VECTOR_BACKEND=weaviate uv run --extra dev pytest -m weaviate tests/test_weaviate_integration.py

ready
1 passed in 4.68s

Post-review verification:

uv run python -m py_compile pdftablesearch/web_server.py pdftablesearch/port_utils.py pdftablesearch/qa.py pdftablesearch/vectorstore.py pdftablesearch/vectorstores/*.py
uv run --extra dev pytest tests/test_vectorstore.py tests/test_core.py tests/test_models.py tests/test_vectorstore_contract.py tests/test_weaviate_store.py tests/test_weaviate_integration.py

45 passed, 1 skipped in 3.64s

VECTOR_BACKEND=weaviate uv run --extra dev pytest -m weaviate tests/test_weaviate_integration.py

1 passed in 4.67s
```

## Verification Gates

Gate 1: Chroma parity still passes.

```bash
uv run pytest tests/test_vectorstore.py tests/test_core.py tests/test_models.py
```

Gate 2: Weaviate contract passes without an external process using fake clients.

```bash
VECTOR_BACKEND=weaviate uv run pytest tests/test_vectorstore_contract.py
```

Gate 3: Embedded Weaviate starts and is ready.

```bash
uv run killports
uv run weaviate
curl http://127.0.0.1:8113/v1/.well-known/ready
```

Gate 4: Integration search works against real Weaviate.

```bash
VECTOR_BACKEND=weaviate uv run pytest -m weaviate
```

Gate 5: Full local app smoke works.

```bash
VECTOR_BACKEND=weaviate uv run qa
```

Manual checks:

- Upload a PDF.
- Confirm table indexing count is non-zero.
- Search table content.
- Run smart search.
- Ask document-level QA.
- End the session and confirm Weaviate objects for that `session_id` are deleted.

## Rollback Plan

- Keep `VECTOR_BACKEND=chroma` available until after Gate 5 passes.
- If Weaviate search regresses, switch env back to `VECTOR_BACKEND=chroma` without changing API/UI code.
- If package splitting fails, keep the monolith with the backend facade and defer workspace migration.
- If embedded Weaviate port conflicts occur, override `WEAVIATE_PORT` and `WEAVIATE_GRPC_PORT`.

## Non-Goals For First Implementation

- Do not encrypt table HTML or chunk text in Weaviate in this first migration. The current Chroma implementation stores those as searchable content, so encryption is a separate privacy/security feature.
- Do not create one Weaviate collection per browser session.
- Do not introduce a real queue or background worker before shared job/session state exists.
- Do not remove Chroma dependency until Weaviate has passed parity and one cleanup pass.
