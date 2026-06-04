"""FastAPI web server for PDFTableSearch React frontend.

Run with::

    uvicorn pdftablesearch.web_server:app --reload --port 8000
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
import uuid
import asyncio
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from contextlib import asynccontextmanager

from dataclasses import dataclass

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from pdftablesearch import PDFProcessor, PDFTableSearch, smart_search
from pdftablesearch.auth import (
    LDAPUser,
    auth_config,
    call_otp_subprocess,
    clear_auth_cookie,
    client_ip,
    decode_pre_auth_jwt,
    get_current_user,
    issue_pre_auth_jwt,
    issue_session_jwt,
    ldap_client_from_settings,
    set_auth_cookie,
    warn_if_insecure_auth_secret,
)
from pdftablesearch.config import get_settings
from pdftablesearch.llm_client import ZaiLLMClient
from pdftablesearch.pii_masking import mask_pii_in_html, mask_pii_text
from pdftablesearch.translation import translate_html
import os

os.environ["HF_HUB_OFFLINE"] = "1"

from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings
from pdftablesearch.models import TableSearchResult
from pdftablesearch.session_store import (
    delete_session as delete_auth_session,
    read_session,
    write_session,
)
from pdftablesearch.vectorstores import create_vector_store as TableVectorStore

from pdftablesearch.table_utils import (
    _HEADER_KEYWORDS, _table_col_count, _table_first_row,
    _row_has_numbers, _row_has_header_keywords,
    _enrich_tables_with_pymupdf, _escape_html, _normalize_text,
    _table_text_content, _table_match_score,
    _extract_top_level_tables_with_nesting, _build_tables_from_pymupdf,
    _detect_multipage_tables, _apply_table_groups, _merge_grouped_tables,
)
from pdftablesearch.doc_processing import (
    _classify_table_type, _tokenize_korean,
    _HEADING_TAGS, _BLOCK_TAGS, _PARA_MIN_CHARS, _PARA_MAX_CHARS,
    _extract_blocks_from_html, _extract_blocks_with_headings,
    _split_long_text, _split_html_by_paragraphs,
)

_sessions: Dict[str, dict] = {}
_embeddings: Optional[SentenceTransformerEmbeddings] = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global _embeddings
    warn_if_insecure_auth_secret()
    # Clean up stale temp directories from previous runs
    import glob as _glob
    import shutil
    for pattern in ["pdf_upload_*", "pdf_data_*", "pdf_docchunks_*"]:
        for d in _glob.glob(os.path.join(tempfile.gettempdir(), pattern)):
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass
    _embeddings = SentenceTransformerEmbeddings()
    yield


app = FastAPI(title="PDFTableSearch API", version="0.1.0", lifespan=lifespan)
_settings = get_settings()
_cors_allowed_origins = [
    origin.strip() for origin in _settings.cors_allowed_origins.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_embeddings() -> SentenceTransformerEmbeddings:
    return _embeddings


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5


class SmartSearchRequest(BaseModel):
    query: str
    pdf_name: Optional[str] = None


class QARequest(BaseModel):
    question: str
    table_html: str
    table_title: Optional[str] = None


class CalculateRequest(BaseModel):
    table_id: str
    question: str


class UnifiedSearchRequest(BaseModel):
    query: str
    pdf_names: Optional[list[str]] = None


class UnifiedFollowupRequest(BaseModel):
    question: str
    context: str
    sources_json: str


class CreateSessionRequest(BaseModel):
    name: Optional[str] = None


class UpdateSessionRequest(BaseModel):
    name: str


class LDAPAuthRequest(BaseModel):
    id: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class OTPAuthRequest(BaseModel):
    pre_auth_token: str
    otp: str


@dataclass
class SessionContext:
    session_id: str
    session: dict[str, Any]


def _get_session(session_id: Optional[str]) -> dict:
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _sessions[session_id]
    session["last_activity"] = datetime.now(timezone.utc).isoformat()
    return session


def _require_owned_session(session_id: Optional[str], current_user: LDAPUser) -> SessionContext:
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    owner_id = session.get("owner_id")
    if owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized for this session")

    session["last_activity"] = datetime.now(timezone.utc).isoformat()
    return SessionContext(session_id=session_id, session=session)


async def get_session_context(
    request: Request,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
) -> SessionContext:
    session_id = x_session_id or request.query_params.get("session_id")
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _sessions[session_id]
    session["last_activity"] = datetime.now(timezone.utc).isoformat()
    return SessionContext(session_id=session_id, session=session)


def _serialize_session_brief(session_id: str, session: dict) -> dict:
    return {
        "session_id": session_id,
        "name": session.get("name", ""),
        "created_at": session.get("created_at", ""),
        "last_activity": session.get("last_activity", ""),
        "pdf_count": len(session.get("pdfs", {})),
        "total_pages": session.get("total_pages", 0),
        "total_tables": sum(
            info.get("table_count", 0) for info in session.get("pdfs", {}).values()
        ),
        "search_count": session.get("search_count", 0),
        "qa_count": session.get("qa_count", 0),
        "pdf_names": list(session.get("pdfs", {}).keys()),
    }


def _serialize_table(result: TableSearchResult) -> dict:
    raw_html = result.table_html or ""
    raw_title = result.table_title or ""
    return {
        "table_id": result.table_id,
        "document_name": result.document_name,
        "page_number": result.page_number,
        "table_title": mask_pii_text(raw_title) if raw_title else raw_title,
        "table_html": mask_pii_in_html(raw_html) if raw_html else raw_html,
        "table_markdown": result.table_markdown,
        "relevance_score": result.relevance_score,
        "rerank_score": result.rerank_score,
        "bounding_box": result.bounding_box,
        "table_type": result.table_type or "기타",
    }


def _format_results(
    search_results: list[tuple[Any, float]],
) -> list[TableSearchResult]:
    results: list[TableSearchResult] = []
    for doc, score in search_results:
        results.append(TableSearchResult.from_langchain_document(doc, score))
    results.sort(key=lambda r: r.relevance_score or float("inf"))
    return results


def _find_table_html(session: dict, table_id: str) -> str:
    """Find table HTML in session by table_id.

    Searches through all uploaded PDFs and their extracted tables.
    """
    for _pdf_name, pdf_info in session.get("pdfs", {}).items():
        for table in pdf_info.get("tables", []):
            if table.get("table_id") == table_id:
                html = table.get("table_html", "")
                if html:
                    return mask_pii_in_html(html)
    raise HTTPException(status_code=404, detail=f"Table '{table_id}' not found in session")


def _transpose_table_html(html: str) -> str:
    """Transpose an HTML table (swap rows and columns) using pandas."""
    try:
        dfs = pd.read_html(html)
    except ValueError:
        return html
    if not dfs:
        return html
    df = dfs[0]
    transposed = df.transpose()
    return transposed.to_html(
        index=False, header=False, classes="table table-bordered"
    )








# ---------------------------------------------------------------------------
# Chunking & indexing
# ---------------------------------------------------------------------------

def _chunk_and_index_session(session_id: str) -> None:
    import shutil

    session = _sessions.get(session_id)
    if not session:
        return
    if session.get("document_chunks_ready"):
        return

    from rank_bm25 import BM25Okapi

    PAGE_SEP_RE = re.compile(
        r"<div[^>]*class=['\"][^'\"]*page-sep[^'\"]*['\"]"
        r"[^>]*data-pn=['\"](\d+)['\"][^>]*>",
        re.IGNORECASE,
    )

    all_chunks: list[str] = []
    all_metadatas: list[dict] = []

    for pdf_name, pdf_info in session.get("pdfs", {}).items():
        html_path = pdf_info.get("html_path")
        if not html_path or not Path(html_path).exists():
            continue

        html_content = Path(html_path).read_text(encoding="utf-8")

        # Split HTML by page separators to preserve page boundaries
        parts = PAGE_SEP_RE.split(html_content)

        if len(parts) <= 1:
            pdf_page_count = pdf_info.get("page_count", 1)
            para_chunks = _split_html_by_paragraphs(html_content, pdf_name, 1)
            if not para_chunks:
                continue
            total = len(para_chunks)
            for i, (text, para_id, section) in enumerate(para_chunks):
                page_estimate = max(1, int(i * pdf_page_count / max(total, 1)) + 1)
                all_chunks.append(text)
                all_metadatas.append({
                    "source_pdf": pdf_name,
                    "chunk_index": len(all_metadatas),
                    "page_number": page_estimate,
                    "pdf_page_count": pdf_page_count,
                    "paragraph_id": re.sub(
                        r"_p\d+_para", f"_p{page_estimate}_para", para_id
                    ),
                    "section_path": section,
                    "doc_type": "text",
                })
            continue

        pdf_page_count = pdf_info.get("page_count", 1)

        # parts[0] is before the first separator (usually empty or title)
        # After that, pairs of (page_number, page_html) from PAGE_SEP_RE.split
        for pi in range(1, len(parts), 2):
            page_num_str = parts[pi]
            page_html = parts[pi + 1] if pi + 1 < len(parts) else ""
            page_num = int(page_num_str)

            para_chunks = _split_html_by_paragraphs(page_html, pdf_name, page_num)
            for text, para_id, section in para_chunks:
                all_chunks.append(text)
                all_metadatas.append({
                    "source_pdf": pdf_name,
                    "chunk_index": len(all_metadatas),
                    "page_number": page_num,
                    "pdf_page_count": pdf_page_count,
                    "paragraph_id": para_id,
                    "section_path": section,
                    "doc_type": "text",
                })

    if not all_chunks:
        return

    old_dir = session.get("doc_chunks_dir", "")
    new_dir = tempfile.mkdtemp(prefix="pdf_docchunks_")
    session["doc_chunks_dir"] = new_dir

    embeddings = _get_embeddings()

    vector_store = TableVectorStore(
        embeddings=embeddings,
        persist_dir=new_dir,
        collection_name=f"doc_chunks_{session_id}",
    )

    docs = []
    for chunk, meta in zip(all_chunks, all_metadatas):
        from langchain_core.documents import Document

        docs.append(Document(page_content=chunk, metadata=meta))

    vector_store.add_documents(docs, skip_existing=False)

    # Build BM25 index for keyword search
    tokenized_corpus = [_tokenize_korean(chunk) for chunk in all_chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    session["bm25_index"] = bm25
    session["bm25_chunks"] = all_chunks
    session["bm25_metadatas"] = all_metadatas

    session["document_chunks_ready"] = True

    if old_dir and old_dir != new_dir:
        try:
            shutil.rmtree(old_dir, ignore_errors=True)
        except Exception:
            pass

















class ConfirmGroupRequest(BaseModel):
    pdf_name: str
    confirmed: list[dict]
    rejected: list[dict]


@app.get("/api/auth/config")
async def auth_config_endpoint() -> JSONResponse:
    return JSONResponse(content=auth_config())


@app.post("/api/auth/ldap")
async def ldap_auth(body: LDAPAuthRequest) -> JSONResponse:
    client = ldap_client_from_settings()
    user = client.authenticate(body.id, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid_credentials")

    return JSONResponse(content={"pre_auth_token": issue_pre_auth_jwt(user)})


@app.post("/api/auth/login")
async def login(body: LoginRequest) -> JSONResponse:
    return await ldap_auth(LDAPAuthRequest(id=body.username, password=body.password))


@app.post("/api/auth/otp")
async def otp(body: OTPAuthRequest, request: Request) -> JSONResponse:
    user_data = decode_pre_auth_jwt(body.pre_auth_token)
    if user_data is None:
        raise HTTPException(status_code=401, detail="session_expired")

    result = await call_otp_subprocess(
        user_id=str(user_data["user_id"]),
        otp=body.otp,
        client_ip_str=client_ip(request),
    )
    if result == "6000":
        raise HTTPException(status_code=401, detail="otp_failed")
    if result != "0":
        raise HTTPException(status_code=500, detail="otp_system_error")

    token, ttl_seconds, jti = issue_session_jwt(user_data)
    stored = await write_session(token, {**user_data, "jti": jti}, ttl_seconds)
    if not stored:
        raise HTTPException(status_code=503, detail="session_store_unavailable")

    response = JSONResponse(content={"redirect": get_settings().auth_ui_url})
    set_auth_cookie(response, token, ttl_seconds)
    return response


@app.post("/api/auth/logout")
async def logout(request: Request) -> JSONResponse:
    token = request.cookies.get(get_settings().auth_cookie_name)
    if token:
        await delete_auth_session(token)
    response = JSONResponse(content={"ok": True})
    clear_auth_cookie(response)
    return response


@app.get("/api/auth/logout")
async def logout_redirect(request: Request) -> Response:
    token = request.cookies.get(get_settings().auth_cookie_name)
    if token:
        await delete_auth_session(token)
    response = Response(status_code=302)
    response.headers["Location"] = f"{get_settings().auth_ui_url}/login"
    clear_auth_cookie(response)
    return response


@app.get("/api/auth/verify")
async def verify_token(request: Request) -> JSONResponse:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_token")
    token = auth_header[7:]
    claims = await read_session(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="invalid_token")
    return JSONResponse(content=claims)


@app.delete("/api/auth/session")
async def delete_token(request: Request) -> JSONResponse:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_token")
    await delete_auth_session(auth_header[7:])
    return JSONResponse(content={"deleted": True})


@app.get("/api/auth/me")
async def me(current_user: LDAPUser = Depends(get_current_user)) -> JSONResponse:
    return JSONResponse(content={"user": current_user.model_dump(), **auth_config()})


@app.post("/api/auth/touch")
async def touch(current_user: LDAPUser = Depends(get_current_user)) -> JSONResponse:
    return JSONResponse(content={"ok": True, "user": current_user.model_dump(), **auth_config()})


@app.post("/api/confirm-table-groups")
async def confirm_table_groups(
    body: ConfirmGroupRequest,
    x_session_id: Optional[str] = Header(None),
) -> JSONResponse:
    session = _get_session(x_session_id)
    pdf_name = body.pdf_name
    if pdf_name not in session.get("pdfs", {}):
        raise HTTPException(status_code=404, detail=f"PDF '{pdf_name}' not found")

    tables = session["pdfs"][pdf_name].get("tables", [])
    by_id = {t["table_id"]: t for t in tables}

    for c in body.confirmed:
        gid = c.get("group_id", "")
        chain_ids = c.get("table_ids", [])
        if not chain_ids:
            continue

        for tid in chain_ids:
            if tid in by_id:
                by_id[tid]["group_id"] = gid

        first = by_id.get(chain_ids[0])
        if first and first.get("table_title"):
            for tid in chain_ids[1:]:
                t = by_id.get(tid)
                if t and not t.get("table_title"):
                    t["table_title"] = first["table_title"]

    _merge_grouped_tables(tables)

    merged_results = []
    confirmed_ids = set()
    for c in body.confirmed:
        for tid in c.get("table_ids", []):
            confirmed_ids.add(tid)
    for t in tables:
        if t.get("merged_table_html") and t["table_id"] in confirmed_ids:
            merged_results.append({
                "table_id": t["table_id"],
                "merged_table_html": t["merged_table_html"],
                "group_table_ids": t.get("group_table_ids", []),
            })

    return JSONResponse(content={"status": "ok", "applied": len(body.confirmed), "merged": merged_results})


@app.get("/api/sessions")
async def list_sessions() -> JSONResponse:
    sessions = [
        _serialize_session_brief(sid, s) for sid, s in _sessions.items()
    ]
    return JSONResponse(content={"sessions": sessions, "total": len(sessions)})


@app.post("/api/sessions")
async def create_session(body: CreateSessionRequest, request: Request) -> JSONResponse:
    session_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    upload_dir = tempfile.mkdtemp(prefix="pdf_upload_")
    data_dir = tempfile.mkdtemp(prefix="pdf_data_")

    session: Dict[str, Any] = {
        "upload_dir": upload_dir,
        "data_dir": data_dir,
        "pdfs": {},
        "searcher": None,
        "name": body.name or "",
        "created_at": now,
        "last_activity": now,
        "total_pages": 0,
        "search_count": 0,
        "qa_count": 0,
        "owner_id": None,
    }

    try:
        current_user_obj = await get_current_user(request)
        session["owner_id"] = current_user_obj.user_id
    except HTTPException:
        pass

    _sessions[session_id] = session

    return JSONResponse(
        content={"session_id": session_id, "name": session["name"]},
        status_code=201,
    )


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> JSONResponse:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _sessions[session_id]
    return JSONResponse(content=_serialize_session_brief(session_id, session))


@app.put("/api/sessions/{session_id}")
async def update_session(session_id: str, body: UpdateSessionRequest) -> JSONResponse:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _sessions[session_id]
    session["name"] = body.name
    session["last_activity"] = datetime.now(timezone.utc).isoformat()
    return JSONResponse(content=_serialize_session_brief(session_id, session))


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str) -> JSONResponse:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _sessions.pop(session_id)
    upload_dir = session.get("upload_dir")
    data_dir = session.get("data_dir")
    if upload_dir:
        shutil.rmtree(upload_dir, ignore_errors=True)
    if data_dir:
        shutil.rmtree(data_dir, ignore_errors=True)
    return JSONResponse(content={"deleted": session_id})


@app.get("/api/documents/pdf")
async def get_document_pdf(
    name: str,
    session_id: Optional[str] = None,
    x_session_id: Optional[str] = Header(None),
):
    from starlette.responses import FileResponse
    sid = session_id or x_session_id
    session = _get_session(sid)
    if name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{name}' not found in session")
    pdf_path = session["pdfs"][name].get("path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    return FileResponse(Path(pdf_path), media_type="application/pdf")


@app.get("/api/documents/page-image")
async def get_page_image(
    name: str,
    page: int = 1,
    dpi: int = 150,
    session_id: Optional[str] = None,
    x_session_id: Optional[str] = Header(None),
):
    """Render a specific PDF page as a PNG image using PyMuPDF."""
    from starlette.responses import Response
    import fitz

    sid = session_id or x_session_id
    session = _get_session(sid)
    if name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{name}' not found")
    pdf_path = session["pdfs"][name].get("path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF file not found")

    try:
        doc = fitz.open(pdf_path)
        page_idx = max(0, min(page - 1, len(doc) - 1))
        pdf_page = doc[page_idx]
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = pdf_page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        doc.close()
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to render page: {exc}")

@app.get("/api/documents/text")
async def get_document_text(
    name: str,
    session_id: Optional[str] = None,
    x_session_id: Optional[str] = Header(None),
):
    import re
    from starlette.responses import Response
    sid = session_id or x_session_id
    session = _get_session(sid)
    if name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{name}' not found in session")
    html_path = session["pdfs"][name].get("html_path")
    if not html_path or not Path(html_path).exists():
        raise HTTPException(status_code=404, detail="HTML content not available")
    html = Path(html_path).read_text(encoding="utf-8")
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\s+', ' ', text).strip()
    text = mask_pii_text(text)
    output_name = Path(name).stem
    return Response(
        content=text,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{output_name}.txt"'},
    )

@app.get("/api/documents/markdown")
async def get_document_markdown(
    name: str,
    session_id: Optional[str] = None,
    x_session_id: Optional[str] = Header(None),
):
    from starlette.responses import Response
    sid = session_id or x_session_id
    session = _get_session(sid)
    if name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{name}' not found in session")
    md_path = session["pdfs"][name].get("md_path")
    if not md_path or not Path(md_path).exists():
        raise HTTPException(status_code=404, detail="Markdown content not available")
    content = Path(md_path).read_text(encoding="utf-8")
    output_name = Path(name).stem
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{output_name}.md"'},
    )

@app.get("/api/documents/tables")
async def get_document_tables(
    name: str,
    session_id: Optional[str] = None,
    x_session_id: Optional[str] = Header(None),
):
    sid = session_id or x_session_id
    session = _get_session(sid)
    if name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{name}' not found in session")
    tables = session["pdfs"][name].get("tables", [])
    seen_ids = set()
    masked_tables = []
    for t in tables:
        tid = t.get("table_id", "")
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        mt = dict(t)
        if mt.get("table_html"):
            mt["table_html"] = mask_pii_in_html(mt["table_html"])
        if mt.get("table_title"):
            mt["table_title"] = mask_pii_text(mt["table_title"])
        if mt.get("merged_table_html"):
            mt["merged_table_html"] = mask_pii_in_html(mt["merged_table_html"])
        masked_tables.append(mt)
    return JSONResponse(content={"tables": masked_tables})

@app.get("/api/documents/html")
async def get_document_html(
    name: str,
    session_id: Optional[str] = None,
    x_session_id: Optional[str] = Header(None),
) -> HTMLResponse:
    sid = session_id or x_session_id
    session = _get_session(sid)
    if name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{name}' not found in session")

    html_path = session["pdfs"][name].get("html_path")
    if not html_path or not Path(html_path).exists():
        upload_dir = session.get("upload_dir", "")
        if upload_dir:
            upload_root = Path(upload_dir)
            for candidate in upload_root.rglob("*.html"):
                html_path = str(candidate)
                session["pdfs"][name]["html_path"] = html_path
                break

    if not html_path or not Path(html_path).exists():
        raise HTTPException(status_code=404, detail=f"HTML content not available for '{name}'")
    html_content = Path(html_path).read_text(encoding="utf-8")
    return HTMLResponse(content=mask_pii_in_html(html_content))


@app.get("/api/documents/page-html")
async def get_page_html(
    name: str,
    page: int = 1,
    session_id: Optional[str] = None,
    x_session_id: Optional[str] = Header(None),
) -> HTMLResponse:
    sid = session_id or x_session_id
    session = _get_session(sid)
    if name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{name}' not found in session")

    pdf_info = session["pdfs"][name]
    html_path = pdf_info.get("html_path")
    if not html_path or not Path(html_path).exists():
        raise HTTPException(status_code=404, detail="HTML content not available")

    from pdftablesearch.translation import split_html_by_pages
    html_content = Path(html_path).read_text(encoding="utf-8")
    pages = split_html_by_pages(html_content)

    for pn, chunk in pages:
        if pn == page:
            return HTMLResponse(content=mask_pii_in_html(chunk.strip()))

    raise HTTPException(status_code=404, detail=f"Page {page} not found")


@app.get("/api/documents/images")
async def get_document_images(
    name: str,
    x_session_id: Optional[str] = Header(None),
) -> JSONResponse:
    """Extract images from PDF's HTML with surrounding context text.

    Converts the PDF with ``image_output="embedded"`` if not already done,
    then parses the HTML to find all ``<img>`` tags with their alt text,
    preceding/following text context, and page number.
    """
    session = _get_session(x_session_id)
    if name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{name}' not found in session")

    pdf_info = session["pdfs"][name]

    # Check if we already have an embedded-HTML version
    embedded_html_path = pdf_info.get("embedded_html_path")
    if not embedded_html_path or not Path(embedded_html_path).exists():
        # Convert PDF with embedded images
        import opendataloader_pdf

        pdf_path = pdf_info["path"]
        output_dir = str(Path(pdf_path).parent / Path(name).stem / "_embedded")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        try:
            opendataloader_pdf.convert(
                input_path=str(pdf_path),
                output_dir=output_dir,
                format="html",
                image_output="embedded",
                image_format="png",
                html_page_separator="<div class='page-sep' data-pn='%page-number%'></div>",
            )
        except TypeError:
            try:
                opendataloader_pdf.convert(
                    input_path=str(pdf_path),
                    output_dir=output_dir,
                    format="html",
                    image_output="embedded",
                    html_page_separator="<div class='page-sep' data-pn='%page-number%'></div>",
                )
            except TypeError:
                try:
                    opendataloader_pdf.convert(
                        input_path=str(pdf_path),
                        output_dir=output_dir,
                        format="html",
                        image_output="embedded",
                    )
                except Exception as exc:
                    raise HTTPException(status_code=500, detail=f"PDF image extraction failed: {exc}")
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"PDF image extraction failed: {exc}")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF image extraction failed: {exc}")

        html_files = list(Path(output_dir).glob("*.html"))
        if not html_files:
            return JSONResponse(content={"images": [], "total": 0})

        embedded_html_path = str(html_files[0])
        session["pdfs"][name]["embedded_html_path"] = embedded_html_path

    from bs4 import BeautifulSoup, NavigableString
    import base64

    page_sep_re = re.compile(
        r"<div[^>]*class=['\"][^'\"]*page-sep[^'\"]*['\"]"
        r"[^>]*data-pn=['\"](\d+)['\"][^>]*>",
        re.IGNORECASE,
    )

    # Use the ORIGINAL HTML (which has page separators) for page mapping,
    # and collect image data from the EMBEDDED HTML.
    # Build a map: alt -> embedded image src (base64 data URI)
    embedded_content = Path(embedded_html_path).read_text(encoding="utf-8")
    embedded_soup = BeautifulSoup(embedded_content, "html.parser")
    embedded_img_map: dict[str, str] = {}
    for eimg in embedded_soup.find_all("img"):
        alt = eimg.get("alt", "")
        src = eimg.get("src", "")
        if alt and src:
            embedded_img_map[alt] = src

    # Also collect image data from the ORIGINAL HTML (external image files)
    # and build a combined map: alt -> base64 data URI
    original_html_path = pdf_info.get("html_path")
    original_content = ""
    original_soup = None
    if original_html_path and Path(original_html_path).exists():
        original_content = Path(original_html_path).read_text(encoding="utf-8")
        original_soup = BeautifulSoup(original_content, "html.parser")

        # Load external images and convert to base64
        original_dir = Path(original_html_path).parent
        for oimg in original_soup.find_all("img"):
            alt = oimg.get("alt", "")
            src = oimg.get("src", "")
            if alt and src and not src.startswith("data:"):
                img_file = original_dir / src
                if img_file.exists():
                    img_bytes = img_file.read_bytes()
                    b64 = base64.b64encode(img_bytes).decode("ascii")
                    suffix = img_file.suffix.lstrip(".") or "png"
                    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(suffix, "image/png")
                    data_uri = f"data:{mime};base64,{b64}"
                    # Prefer embedded version if available, else use file version
                    if alt not in embedded_img_map:
                        embedded_img_map[alt] = data_uri

    # Use original HTML for parsing (has page separators and all images)
    parse_content = original_content or embedded_content
    parse_soup = original_soup or embedded_soup

    img_tags = parse_soup.find_all("img")

    images = []
    for idx, img in enumerate(img_tags):
        alt = img.get("alt", f"Image {idx + 1}")

        # Get the actual image data from our combined map
        src = embedded_img_map.get(alt, img.get("src", ""))

        # Skip tiny tracking/spacer images (data URIs shorter than ~500 chars are likely spacers)
        if src.startswith("data:") and len(src) < 500:
            continue
        # Skip if no image data available
        if not src:
            continue

        # Find preceding meaningful text — check siblings, then parent's siblings
        prev_text = ""
        # First check direct siblings of the image
        for sib in img.previous_siblings:
            if isinstance(sib, NavigableString):
                t = sib.strip()
                if t and len(t) > 2:
                    prev_text = t[-200:]
                    break
            elif hasattr(sib, "get_text"):
                t = sib.get_text(strip=True)
                if t and len(t) > 2:
                    prev_text = t[-200:]
                    break
        # If no text found, check parent's siblings (e.g., <figure> wrapping <img>)
        if not prev_text and img.parent and img.parent.name in ("figure", "div", "span"):
            for sib in img.parent.previous_siblings:
                if isinstance(sib, NavigableString):
                    t = sib.strip()
                    if t and len(t) > 2:
                        prev_text = t[-200:]
                        break
                elif hasattr(sib, "get_text"):
                    t = sib.get_text(strip=True)
                    if t and len(t) > 2:
                        prev_text = t[-200:]
                        break

        # Find following meaningful text — same approach
        next_text = ""
        for sib in img.next_siblings:
            if isinstance(sib, NavigableString):
                t = sib.strip()
                if t and len(t) > 2:
                    next_text = t[:200]
                    break
            elif hasattr(sib, "get_text"):
                t = sib.get_text(strip=True)
                if t and len(t) > 2:
                    next_text = t[:200]
                    break
        if not next_text and img.parent and img.parent.name in ("figure", "div", "span"):
            for sib in img.parent.next_siblings:
                if isinstance(sib, NavigableString):
                    t = sib.strip()
                    if t and len(t) > 2:
                        next_text = t[:200]
                        break
                elif hasattr(sib, "get_text"):
                    t = sib.get_text(strip=True)
                    if t and len(t) > 2:
                        next_text = t[:200]
                        break

        # Check if inside a table
        parent_table = img.find_parent("table")
        table_context = None
        if parent_table:
            parent_td = img.find_parent("td") or img.find_parent("th")
            cell_text = parent_td.get_text(strip=True)[:200] if parent_td else ""
            caption = parent_table.find("caption")
            caption_text = caption.get_text(strip=True)[:200] if caption else ""
            table_context = {"cell_text": cell_text, "caption": caption_text}

        # Determine page number from parse_content (original HTML has page separators)
        page_num = 1
        alt_attr = img.get("alt", "")
        if alt_attr and parse_content:
            # Search for the image tag by alt attribute in raw HTML
            alt_pattern = re.compile(
                rf'<img[^>]*alt=[\'"]{re.escape(alt_attr)}[\'"][^>]*>',
                re.IGNORECASE,
            )
            alt_match = alt_pattern.search(parse_content)
            if alt_match:
                img_pos = alt_match.start()
                # Find the last page-sep before this image's position
                for sep_match in page_sep_re.finditer(parse_content):
                    if sep_match.start() < img_pos:
                        page_num = int(sep_match.group(1))

        images.append({
            "index": idx,
            "alt": alt,
            "src": src,
            "prev_text": prev_text,
            "next_text": next_text,
            "page": page_num,
            "in_table": parent_table is not None,
            "table_context": table_context,
        })

    # Generate page images via PyMuPDF (full page, moderate DPI)
    pdf_path = pdf_info["path"]
    import fitz as _fitz

    _doc = _fitz.open(pdf_path)
    page_image_cache: dict[int, str] = {}

    zoom = 150 / 72  # 150 DPI — readable but not oversized
    mat = _fitz.Matrix(zoom, zoom)

    for img_entry in images:
        pn = img_entry["page"]
        if pn not in page_image_cache:
            page_idx = max(0, min(pn - 1, len(_doc) - 1))
            pdf_page = _doc[page_idx]
            pix = pdf_page.get_pixmap(matrix=mat)
            png_bytes = pix.tobytes("png")
            b64 = base64.b64encode(png_bytes).decode("ascii")
            page_image_cache[pn] = f"data:image/png;base64,{b64}"
        img_entry["page_image_src"] = page_image_cache[pn]

    _doc.close()

    return JSONResponse(content={"images": images, "total": len(images)})


@app.post("/api/upload")
async def upload_pdfs(
    files: List[UploadFile] = File(...),
    x_session_id: Optional[str] = Header(None),
) -> JSONResponse:
    session_id = x_session_id or uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()

    if session_id in _sessions:
        session = _sessions[session_id]
        upload_dir = session["upload_dir"]
        data_dir = session["data_dir"]
    else:
        upload_dir = tempfile.mkdtemp(prefix="pdf_upload_")
        data_dir = tempfile.mkdtemp(prefix="pdf_data_")
        doc_chunks_dir = tempfile.mkdtemp(prefix="pdf_docchunks_")
        session: Dict[str, Any] = {
            "upload_dir": upload_dir,
            "data_dir": data_dir,
            "doc_chunks_dir": doc_chunks_dir,
            "pdfs": {},
            "searcher": None,
            "name": "",
            "created_at": now,
            "last_activity": now,
            "total_pages": 0,
            "search_count": 0,
            "qa_count": 0,
        }
        _sessions[session_id] = session

    session_has_existing_pdfs = len(session.get("pdfs", {})) > 0

    pdf_results: Dict[str, dict] = {}
    total_tables = 0
    all_docs: list = []

    for upload in files:
        filename = upload.filename
        if not filename:
            continue

        dest = Path(upload_dir) / filename
        with open(dest, "wb") as f:
            content = await upload.read()
            f.write(content)

        try:
            pdf_output_dir = str(Path(upload_dir) / Path(filename).stem)
            processor = PDFProcessor()
            processor.load_documents(str(dest), use_hybrid=True, output_dir=pdf_output_dir)
            documents = processor.get_documents()

            standard_html_path = processor.convert_standard(str(dest), output_dir=pdf_output_dir)

            html_path: Optional[str] = None
            md_path: Optional[str] = None
            page_count: int = 0
            conv_dir = Path(pdf_output_dir)
            if conv_dir.exists():
                html_files = list(conv_dir.rglob("*.html"))
                if html_files:
                    html_path = str(html_files[0])
                md_files = list(conv_dir.rglob("*.md"))
                if md_files:
                    md_path = str(md_files[0])

            if documents:
                max_page = max((doc.metadata.get("page_number", 0) for doc in documents), default=0)
                page_count = max_page
        except Exception as exc:
            pdf_results[filename] = {
                "table_count": 0,
                "error": str(exc),
            }
            continue

        hybrid_tables = [
            TableSearchResult.from_langchain_document(doc, 0.0).to_dict()
            for doc in documents
        ]

        final_tables = _build_tables_from_pymupdf(
            str(dest),
            hybrid_tables,
            str(standard_html_path) if standard_html_path else None,
        )

        if not final_tables:
            final_tables = hybrid_tables

        for table in final_tables:
            table["table_type"] = _classify_table_type(
                table.get("table_title"), table.get("table_html")
            )

        table_count = len(final_tables)
        total_tables += table_count
        all_docs.extend(documents)

        pymupdf_only_count = 0
        for ft in final_tables:
            if ft.get("_source") == "pymupdf":
                from langchain_core.documents import Document as LCDocument
                ft_title = ft.get("table_title") or ""
                ft_html = ft.get("table_html") or ""
                content_parts = []
                if ft_title:
                    content_parts.append(ft_title)
                if ft_html:
                    content_parts.append(ft_html)
                content = "\n".join(content_parts)
                doc_meta = {
                    "page_number": ft.get("page_number", 0),
                    "bounding_box": ft.get("bounding_box", [0, 0, 0, 0]),
                    "table_id": ft.get("table_id", ""),
                    "document_name": ft.get("document_name", filename),
                    "table_html": ft_html,
                }
                if ft_title:
                    doc_meta["table_title"] = ft_title
                all_docs.append(LCDocument(page_content=content, metadata=doc_meta))
                pymupdf_only_count += 1


        session["pdfs"][filename] = {
            "path": str(dest),
            "table_count": table_count,
            "html_path": html_path,
            "md_path": md_path,
            "page_count": page_count,
            "tables": final_tables,
        }

        pdf_results[filename] = {
            "table_count": table_count,
            "page_count": page_count,
        }

    session["total_pages"] = sum(
        info.get("page_count", 0) for info in session["pdfs"].values()
    )
    session["last_activity"] = now
    session["document_chunks_ready"] = False

    try:
        _chunk_and_index_session(session_id)
    except Exception:
        pass

    if total_tables > 0 and all_docs:
        embeddings = _get_embeddings()
        vector_store = TableVectorStore(
            embeddings=embeddings,
            persist_dir=data_dir,
        )
        # Only reset if this is a fresh session (no existing PDFs before this upload)
        if not session_has_existing_pdfs:
            try:
                vector_store.reset()
            except Exception:
                pass
        vector_store.add_documents(all_docs)

    _sessions[session_id] = session

    # Detect multi-page table continuations
    all_suggestions: list[dict] = []

    for fname, finfo in session["pdfs"].items():
        tables = finfo.get("tables", [])
        pairs = _detect_multipage_tables(tables)
        for pair in pairs:
            pair["pdf_name"] = fname
            all_suggestions.append(pair)

    return JSONResponse(
        content={
            "session_id": session_id,
            "pdfs": pdf_results,
            "total_tables": total_tables,
            "total_pages": sum(info.get("page_count", 0) for info in session["pdfs"].values()),
            "table_group_suggestions": all_suggestions,
        }
    )


@app.get("/api/pdfs")
async def list_pdfs(x_session_id: Optional[str] = Header(None)) -> JSONResponse:
    session = _get_session(x_session_id)

    pdfs = [
        {"name": name, "table_count": info["table_count"], "page_count": info.get("page_count", 0)}
        for name, info in session["pdfs"].items()
    ]
    total_tables = sum(info["table_count"] for info in session["pdfs"].values())
    total_pages = sum(info.get("page_count", 0) for info in session["pdfs"].values())

    return JSONResponse(content={"pdfs": pdfs, "total_tables": total_tables, "total_pages": total_pages})


@app.delete("/api/pdfs/{filename}")
async def delete_pdf(
    filename: str,
    x_session_id: Optional[str] = Header(None),
) -> JSONResponse:
    session = _get_session(x_session_id)

    if filename not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{filename}' not found in session")

    pdf_info = session["pdfs"].pop(filename)
    pdf_path = pdf_info.get("path")
    if pdf_path:
        Path(pdf_path).unlink(missing_ok=True)

    pdfs = [
        {"name": name, "table_count": info["table_count"]}
        for name, info in session["pdfs"].items()
    ]
    total_tables = sum(info["table_count"] for info in session["pdfs"].values())

    return JSONResponse(content={"pdfs": pdfs, "total_tables": total_tables})


@app.post("/api/search")
async def search(
    body: SearchRequest,
    x_session_id: Optional[str] = Header(None),
) -> JSONResponse:
    session = _get_session(x_session_id)
    session["search_count"] = session.get("search_count", 0) + 1
    start = time.time()

    data_dir = session["data_dir"]
    if not session["pdfs"]:
        return JSONResponse(
            content={"results": [], "total": 0, "time_seconds": 0.0}
        )

    try:
        embeddings = _get_embeddings()
        vector_store = TableVectorStore(
            embeddings=embeddings,
            persist_dir=data_dir,
        )

        search_results = vector_store.similarity_search(
            query=body.query,
            k=body.max_results,
        )
    except Exception as exc:
        return JSONResponse(
            content={"results": [], "total": 0, "time_seconds": 0.0, "error": f"Search failed: {exc}"}
        )

    elapsed = time.time() - start
    results = [_serialize_table(r) for r in _format_results(search_results)]

    return JSONResponse(
        content={
            "results": results,
            "total": len(results),
            "time_seconds": round(elapsed, 2),
        }
    )


@app.post("/api/smart-search")
async def smart_search_endpoint(
    body: SmartSearchRequest,
    x_session_id: Optional[str] = Header(None),
) -> StreamingResponse:
    session = _get_session(x_session_id)
    session["search_count"] = session.get("search_count", 0) + 1

    pdf_name = body.pdf_name
    if pdf_name and pdf_name in session["pdfs"]:
        pdf_path = session["pdfs"][pdf_name]["path"]
    else:
        if not session["pdfs"]:
            raise HTTPException(status_code=400, detail="No PDFs uploaded in this session")
        first_pdf = next(iter(session["pdfs"].values()))
        pdf_path = first_pdf["path"]

    data_dir = session["data_dir"]
    queue: list[str] = []

    def progress_callback(phase: str, message: str, pct: int) -> None:
        event_data = json.dumps(
            {"phase": phase, "message": message, "pct": pct},
            ensure_ascii=False,
        )
        queue.append(f"event: progress\ndata: {event_data}\n\n")

    def generate():
        try:
            embeddings = _get_embeddings()
            vector_store = TableVectorStore(
                embeddings=embeddings,
                persist_dir=data_dir,
            )

            progress_callback("vector", "벡터 검색 중...", 20)
            raw_results = vector_store.similarity_search(query=body.query, k=20)
            candidates = _format_results(raw_results)

            if not candidates:
                for evt in queue:
                    yield evt
                error_data = json.dumps(
                    {"error": "검색 결과가 없습니다."}, ensure_ascii=False,
                )
                yield f"event: error\ndata: {error_data}\n\n"
                return

            progress_callback("vector", f"벡터 검색 완료: {len(candidates)}개 후보", 50)

            if len(candidates) == 1:
                progress_callback("done", "검색 완료 (후보 1개)", 100)
                for evt in queue:
                    yield evt
                result_data = json.dumps(
                    {"result": _serialize_table(candidates[0]), "vector_results": []},
                    ensure_ascii=False,
                )
                yield f"event: result\ndata: {result_data}\n\n"
                return

            progress_callback("llm", f"AI 분석 중... ({len(candidates)}개 후보 평가)", 70)

            from pdftablesearch.smart_search import _prepare_candidates, _run_llm_selection
            selected = _run_llm_selection(
                query=body.query,
                candidates_results=candidates,
                llm_model="glm-4.7",
                api_key=None,
            )

            if selected is None:
                selected = candidates[0]
                progress_callback("done", "AI 실패, 벡터 검색 결과로 대체", 100)
            else:
                progress_callback("done", "AI 선택 완료!", 100)

            for evt in queue:
                yield evt

            vector_extras = [
                _serialize_table(r)
                for r in candidates
                if r.table_id != selected.table_id
            ][:2]

            result_data = json.dumps(
                {
                    "result": _serialize_table(selected),
                    "vector_results": vector_extras,
                },
                ensure_ascii=False,
            )
            yield f"event: result\ndata: {result_data}\n\n"

        except Exception as exc:
            for evt in queue:
                yield evt
            error_data = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/qa")
async def qa(
    body: QARequest,
    x_session_id: Optional[str] = Header(None),
) -> StreamingResponse:
    session = _get_session(x_session_id)
    session["qa_count"] = session.get("qa_count", 0) + 1

    import hashlib
    table_id_key = body.table_title or hashlib.md5(body.table_html[:200].encode()).hexdigest()
    qa_key = hashlib.md5(f"{table_id_key}:{body.question}".encode()).hexdigest()
    sid = x_session_id

    if "qa_results" not in session:
        session["qa_results"] = {}
    session["qa_results"][qa_key] = {"question": body.question, "answer": "", "done": False, "table_id": table_id_key}

    table_title = body.table_title or "(제목 없음)"
    today = date.today()

    transpose_keywords = ["가로", "세로", "축을 변경", "transpose", "바꿔", "행과 열", "열과 행", "가로축", "세로축"]
    is_transpose = any(kw in body.question for kw in transpose_keywords)

    if is_transpose and body.table_html:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(body.table_html, "html.parser")
        table = soup.find("table")
        if table:
            rows = table.find_all("tr")
            matrix = []
            for row in rows:
                cells = [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
                if cells:
                    matrix.append(cells)

            if matrix:
                col_count = max(len(r) for r in matrix)
                for r in matrix:
                    r.extend([""] * (col_count - len(r)))

                transposed = list(zip(*matrix))

                md_lines = []
                header = "| " + " | ".join(str(c) if c else " " for c in transposed[0]) + " |"
                separator = "|" + "|".join("---" for _ in transposed[0]) + "|"
                md_lines = [header, separator]
                for row in transposed[1:]:
                    md_lines.append("| " + " | ".join(str(c) if c else " " for c in row) + " |")

                transposed_md = "\n".join(md_lines)

                done_key = qa_key
                session["qa_results"][done_key]["answer"] = f"표의 가로/세로축을 변경하였습니다:\n\n{transposed_md}"
                session["qa_results"][done_key]["done"] = True

                async def direct_transpose_response():
                    yield f"data: {json.dumps({'done': True, 'qa_key': qa_key}, ensure_ascii=False)}\n\n"

                return StreamingResponse(
                    direct_transpose_response(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )

    system_prompt = (
        f"You are a data analyst assistant. "
        f"Given a user question and an HTML table, "
        f"provide a clear, accurate answer in Korean.\n\n"
        f"Today is {today}.\n\n"
        f"Rules:\n"
        f"1. Answer based ONLY on the provided table data\n"
        f"2. Use specific numbers from the table when possible\n"
        f"3. If the table doesn't contain enough information, say so clearly\n"
        f"4. Respond in Korean\n"
        f"5. Do NOT include HTML tags in your answer. Use plain text or markdown tables only.\n"
        f"6. When presenting data, use markdown table format (| col1 | col2 |) instead of HTML."
    )

    user_prompt = (
        f"User Question: {body.question}\n\n"
        f"Table (HTML):\n{body.table_html[:4000]}\n\n"
        f"Table Title: {table_title}\n\n"
        f"Answer:"
    )

    result_queue: asyncio.Queue = asyncio.Queue()

    async def background_llm():
        client = ZaiLLMClient(max_retries=6)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        accumulated = ""
        try:
            for chunk in client._llm.stream(messages):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token:
                    accumulated += token
                    session["qa_results"][qa_key]["answer"] = accumulated
                    await result_queue.put(token)
            session["qa_results"][qa_key]["done"] = True
        except Exception as exc:
            session["qa_results"][qa_key]["answer"] = f"오류: {exc}"
            session["qa_results"][qa_key]["done"] = True
        await result_queue.put(None)

    asyncio.create_task(background_llm())

    async def sse_generate():
        while True:
            try:
                token = await asyncio.wait_for(result_queue.get(), timeout=0.3)
                if token is None:
                    yield f"data: {json.dumps({'done': True, 'qa_key': qa_key}, ensure_ascii=False)}\n\n"
                    break
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                if session["qa_results"][qa_key]["done"]:
                    yield f"data: {json.dumps({'done': True, 'qa_key': qa_key}, ensure_ascii=False)}\n\n"
                    break

    return StreamingResponse(
        sse_generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/qa-results")
async def get_qa_results(
    x_session_id: Optional[str] = Header(None),
) -> JSONResponse:
    session = _get_session(x_session_id)
    results = []
    for qa_key, qa_data in session.get("qa_results", {}).items():
        results.append({
            "qa_key": qa_key,
            "question": qa_data["question"],
            "answer": qa_data["answer"],
            "done": qa_data["done"],
        })
    return JSONResponse(content={"results": results})


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok", "sessions": len(_sessions)})


@app.post("/api/table-transpose/{table_id}")
async def table_transpose(
    table_id: str,
    x_session_id: Optional[str] = Header(None),
) -> JSONResponse:
    session = _get_session(x_session_id)
    html = _find_table_html(session, table_id)
    transposed_html = _transpose_table_html(html)
    return JSONResponse(content={"html": transposed_html})


@app.post("/api/table-calculate")
async def table_calculate(
    body: CalculateRequest,
    x_session_id: Optional[str] = Header(None),
) -> StreamingResponse:
    session = _get_session(x_session_id)
    table_html = _find_table_html(session, body.table_id)

    try:
        dfs = pd.read_html(table_html)
        df = dfs[0] if dfs else None
    except ValueError:
        df = None

    if df is None:
        raise HTTPException(status_code=422, detail="Could not parse table data")

    csv_summary = df.to_csv(index=False)
    column_info = json.dumps(df.dtypes.apply(str).to_dict(), ensure_ascii=False)

    system_prompt = (
        "You are a data analyst. Given a table (CSV) and a question, "
        "perform the requested calculation and respond in JSON with two fields: "
        '"result" (the numeric answer as a string) and "explanation" (a brief '
        "Korean explanation of how you calculated it).\n\n"
        "Rules:\n"
        "1. Base your answer ONLY on the provided table data\n"
        "2. Show the calculation steps in the explanation\n"
        "3. Respond in valid JSON: {\"result\": \"...\", \"explanation\": \"...\"}\n"
        "4. Keep the explanation concise (1-2 sentences)"
    )

    user_prompt = (
        f"Question: {body.question}\n\n"
        f"Column types: {column_info}\n\n"
        f"Table data (CSV):\n{csv_summary[:4000]}\n\n"
        f"Answer:"
    )

    def generate():
        try:
            client = ZaiLLMClient(max_retries=6)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            for chunk in client._llm.stream(messages):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token:
                    data = json.dumps({"token": token}, ensure_ascii=False)
                    yield f"data: {data}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            data = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class AskDocumentRequest(BaseModel):
    question: str


@app.post("/api/ask-document")
async def ask_document(
    body: AskDocumentRequest,
    x_session_id: Optional[str] = Header(None),
) -> StreamingResponse:
    session = _get_session(x_session_id)
    session["qa_count"] = session.get("qa_count", 0) + 1

    if not session.get("document_chunks_ready"):
        _chunk_and_index_session(x_session_id)

    embeddings = _get_embeddings()

    vector_store = TableVectorStore(
        embeddings=embeddings,
        persist_dir=session["doc_chunks_dir"],
        collection_name=f"doc_chunks_{x_session_id}",
    )

    query = body.question
    k = 8  # retrieve more candidates for fusion

    # --- Vector search ---
    vector_results = vector_store.similarity_search(query=query, k=k)
    # vector_results: list of (Document, score)

    # --- BM25 keyword search ---
    bm25 = session.get("bm25_index")
    bm25_chunks = session.get("bm25_chunks", [])
    bm25_metadatas = session.get("bm25_metadatas", [])

    bm25_results: list[tuple[int, float]] = []
    if bm25 and bm25_chunks:
        tokenized_query = _tokenize_korean(query)
        scores = bm25.get_scores(tokenized_query)
        # Get top-k indices sorted by score
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        bm25_results = [(idx, scores[idx]) for idx in top_indices if scores[idx] > 0]

    # --- Reciprocal Rank Fusion ---
    # Merge vector + BM25 results using RRF
    rrf_k = 60  # constant for RRF
    rrf_scores: dict[int, float] = {}

    for rank, (doc, _score) in enumerate(vector_results):
        # Find chunk index by matching content
        chunk_text = doc.page_content
        for idx, c in enumerate(bm25_chunks):
            if c == chunk_text:
                rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)
                break
        else:
            # Not found in bm25_chunks, add as new entry
            idx = len(bm25_chunks)
            bm25_chunks.append(chunk_text)
            bm25_metadatas.append(doc.metadata)
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)

    for rank, (idx, _score) in enumerate(bm25_results):
        rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)

    # Sort by RRF score, take top 5
    fused_indices = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:5]

    contexts = []
    sources = []
    for idx in fused_indices:
        chunk_text = bm25_chunks[idx]
        meta = bm25_metadatas[idx] if idx < len(bm25_metadatas) else {}
        contexts.append(chunk_text)
        sources.append({
            "pdf": meta.get("source_pdf", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "page_number": meta.get("page_number", 1),
            "pdf_page_count": meta.get("pdf_page_count", 1),
            "paragraph_id": meta.get("paragraph_id", ""),
            "text": chunk_text,
        })

    context_text = "\n\n---\n\n".join(
        f"[출처{i+1}] {c}" for i, c in enumerate(contexts)
    )

    system_prompt = (
        "당신은 전문적인 금융 문서 분석 어시스턴트입니다. 아래 [출처N]으로 표시된 문서 내용만을 기반으로 질문에 답변하세요.\n\n"
        "규칙:\n"
        "1. 문서에 없는 내용은 추측하지 마세요\n"
        "2. 구체적인 수치, 날짜, 업체명 등을 정확히 인용하세요\n"
        "3. 한국어로 존댓말(~습니다, ~합니다, ~세요)을 사용하여 답변하세요\n"
        "4. 충분히 상세하게 답변하세요. 수치가 있다면 구체적인 값을 포함하고, 추이나 변화가 있다면 그 내용도 함께 설명하세요\n"
        "5. 실제 답변에 사용한 출처 번호만 답변 마지막 줄에 '사용출처: 1,3' 형식으로 반드시 표시하세요"
    )

    user_prompt = (
        f"질문: {body.question}\n\n"
        f"참고 문서 내용:\n{context_text[:6000]}\n\n"
        f"답변:"
    )

    def generate():
        try:
            import time as _time
            client = ZaiLLMClient(max_retries=2)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            # Retry loop for 429 rate limit
            max_attempts = 5
            accumulated = ""
            for attempt in range(max_attempts):
                try:
                    for chunk in client._llm.stream(messages):
                        token = chunk.content if hasattr(chunk, "content") else str(chunk)
                        if token:
                            accumulated += token
                            data = json.dumps({"token": token}, ensure_ascii=False)
                            yield f"data: {data}\n\n"
                    break  # success, exit retry loop
                except Exception as stream_exc:
                    err_msg = str(stream_exc)
                    if "429" in err_msg and attempt < max_attempts - 1:
                        wait = 15 * (attempt + 1)
                        yield f"data: {json.dumps({'token': f'[재시도 중... {wait}초 대기 ({attempt+1}/{max_attempts})]'}, ensure_ascii=False)}\n\n"
                        _time.sleep(wait)
                        accumulated = ""
                        continue
                    raise

            used_match = re.search(r'사용출처:\s*([\d,\s]+)', accumulated)
            if used_match:
                used_indices = [int(x.strip()) - 1 for x in used_match.group(1).split(',') if x.strip().isdigit()]
                filtered_sources = [sources[i] for i in used_indices if 0 <= i < len(sources)]
            else:
                filtered_sources = sources

            sources_data = json.dumps({"sources": filtered_sources}, ensure_ascii=False)
            yield f"data: {sources_data}\n\n"

            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            data = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class TranslateRequest(BaseModel):
    pdf_name: str
    source_lang: str = "ko"
    target_lang: str = "en"


@app.post("/api/translate-html")
async def translate_html_pages(
    body: TranslateRequest,
    x_session_id: Optional[str] = Header(None),
) -> StreamingResponse:
    session = _get_session(x_session_id)
    if body.pdf_name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{body.pdf_name}' not found")

    pdf_info = session["pdfs"][body.pdf_name]
    html_path = pdf_info.get("html_path")
    if not html_path or not Path(html_path).exists():
        raise HTTPException(status_code=404, detail="HTML content not available")

    import queue as _queue
    import threading
    import tempfile

    from pdftablesearch.translation import translate_html_by_pages

    output_dir = Path(pdf_info.get("upload_dir", tempfile.mkdtemp())) / "translated"
    output_dir.mkdir(parents=True, exist_ok=True)

    result_queue: _queue.Queue[dict] = _queue.Queue()

    def _on_page_done(page_num: int, total_pages: int, original_html: str, translated_html: str) -> None:
        result_queue.put({
            "type": "page_done",
            "page": page_num,
            "total_pages": total_pages,
            "original_html": original_html,
            "translated_html": translated_html,
        })

    def _run():
        try:
            translate_html_by_pages(
                html_path=html_path,
                output_dir=str(output_dir),
                source_lang=body.source_lang,
                target_lang=body.target_lang,
                on_page_done=_on_page_done,
            )
            result_queue.put({"type": "done"})
        except Exception as exc:
            result_queue.put({"type": "error", "error": str(exc)})

    threading.Thread(target=_run, daemon=True).start()

    def generate():
        while True:
            try:
                data = result_queue.get(timeout=1.0)
            except _queue.Empty:
                yield ": heartbeat\n\n"
                continue

            event_type = data.pop("type")
            yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

            if event_type in ("done", "error"):
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/translated-page")
async def get_translated_page(
    name: str,
    page: int = 1,
    x_session_id: Optional[str] = Header(None),
) -> HTMLResponse:
    session = _get_session(x_session_id)
    if name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{name}' not found")

    pdf_info = session["pdfs"][name]
    upload_dir = pdf_info.get("upload_dir", "")
    translated_file = Path(upload_dir) / "translated" / f"page_{page}.html"

    if not translated_file.exists():
        raise HTTPException(status_code=404, detail=f"Translated page {page} not found. Run translate first.")

    return HTMLResponse(content=translated_file.read_text(encoding="utf-8"))


@app.post("/api/translate")
async def translate_document(
    body: TranslateRequest,
    x_session_id: Optional[str] = Header(None),
) -> StreamingResponse:
    """Translate PDF text to target language, streaming each chunk via SSE.

    SSE events:
        ``chunk_done`` — ``{"chunk", "total_chunks", "translated_text"}`
        ``done``       — ``{"total_chunks", "full_text"}`
        ``error``      — ``{"error"}`
    """
    session = _get_session(x_session_id)
    if body.pdf_name not in session["pdfs"]:
        raise HTTPException(status_code=404, detail=f"PDF '{body.pdf_name}' not found")

    pdf_info = session["pdfs"][body.pdf_name]
    html_path = pdf_info.get("html_path")
    if not html_path or not Path(html_path).exists():
        raise HTTPException(status_code=404, detail="HTML content not available")

    import queue as _queue
    import threading

    from pdftablesearch.translation import translate_text_chunks

    # Extract plain text from HTML
    html = Path(html_path).read_text(encoding="utf-8")
    import re as _re
    text = _re.sub(r'<[^>]+>', ' ', html)
    text = _re.sub(r'\s+', ' ', text).strip()

    if not text:
        raise HTTPException(status_code=400, detail="No text content found")

    result_queue: _queue.Queue[dict] = _queue.Queue()

    def _on_chunk_done(chunk_idx: int, total_chunks: int, translated_text: str) -> None:
        result_queue.put({
            "type": "chunk_done",
            "chunk": chunk_idx,
            "total_chunks": total_chunks,
            "translated_text": translated_text,
        })

    def _run():
        try:
            full_text = translate_text_chunks(
                text=text,
                source_lang=body.source_lang,
                target_lang=body.target_lang,
                on_chunk_done=_on_chunk_done,
            )
            result_queue.put({"type": "done", "full_text": full_text})
        except Exception as exc:
            result_queue.put({"type": "error", "error": str(exc)})

    threading.Thread(target=_run, daemon=True).start()

    def generate():
        while True:
            try:
                data = result_queue.get(timeout=1.0)
            except _queue.Empty:
                yield ": heartbeat\n\n"
                continue

            event_type = data.pop("type")
            yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

            if event_type in ("done", "error"):
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/translate/status/{job_id}")
async def translate_status(job_id: str) -> JSONResponse:
    # Kept for backward compatibility — returns a stub response.
    return JSONResponse(content={"status": "deprecated"})


@app.get("/api/translate/result/{job_id}")
async def translate_html_file(job_id: str) -> JSONResponse:
    # Kept for backward compatibility — returns a stub response.
    return JSONResponse(content={"status": "deprecated"})


# ---------------------------------------------------------------------------
# Unified Search (문서 검색) — combines table + text search
# ---------------------------------------------------------------------------


@app.post("/api/unified-search")
async def unified_search_endpoint(
    body: UnifiedSearchRequest,
    x_session_id: Optional[str] = Header(None),
) -> StreamingResponse:
    session = _get_session(x_session_id)

    # Ensure text chunks are indexed
    if not session.get("document_chunks_ready"):
        _chunk_and_index_session(x_session_id or "")

    embeddings = _get_embeddings()
    queue: list[str] = []

    def progress_callback(phase: str, message: str, pct: int) -> None:
        event_data = json.dumps(
            {"phase": phase, "message": message, "pct": pct},
            ensure_ascii=False,
        )
        queue.append(f"event: progress\ndata: {event_data}\n\n")

    def generate():
        try:
            # --- Phase 1: Vector search on pdf_tables ---
            progress_callback("vector", "문서 검색 중...", 20)
            table_store = TableVectorStore(
                embeddings=embeddings,
                persist_dir=session["data_dir"],
            )
            table_results = table_store.similarity_search(query=body.query, k=15)

            # --- Phase 2: Hybrid search on doc_chunks ---
            progress_callback("text", "텍스트 검색 중...", 40)
            doc_store = TableVectorStore(
                embeddings=embeddings,
                persist_dir=session["doc_chunks_dir"],
                collection_name=f"doc_chunks_{x_session_id}",
            )
            doc_vector_results = doc_store.similarity_search(query=body.query, k=8)

            # BM25 keyword search
            bm25 = session.get("bm25_index")
            bm25_chunks: list[str] = session.get("bm25_chunks", [])
            bm25_metadatas: list[dict] = session.get("bm25_metadatas", [])

            bm25_results: list[tuple[int, float]] = []
            if bm25 and bm25_chunks:
                tokenized_query = _tokenize_korean(body.query)
                scores = bm25.get_scores(tokenized_query)
                top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:8]
                bm25_results = [(idx, scores[idx]) for idx in top_indices if scores[idx] > 0]

            # --- Unified RRF fusion (table + text combined) ---
            rrf_k = 60
            rrf_scores: dict[int, float] = {}
            rrf_is_table: dict[int, bool] = {}

            # Table vector results → unified pool
            for rank, (doc, _score) in enumerate(table_results):
                chunk_text = doc.page_content
                for idx, c in enumerate(bm25_chunks):
                    if c == chunk_text:
                        rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)
                        rrf_is_table[idx] = True
                        break
                else:
                    idx = len(bm25_chunks)
                    bm25_chunks.append(chunk_text)
                    bm25_metadatas.append(doc.metadata)
                    rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)
                    rrf_is_table[idx] = True

            # Text vector results → unified pool
            for rank, (doc, _score) in enumerate(doc_vector_results):
                chunk_text = doc.page_content
                for idx, c in enumerate(bm25_chunks):
                    if c == chunk_text:
                        rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)
                        if idx not in rrf_is_table:
                            rrf_is_table[idx] = False
                        break
                else:
                    idx = len(bm25_chunks)
                    bm25_chunks.append(chunk_text)
                    bm25_metadatas.append(doc.metadata)
                    rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)
                    rrf_is_table[idx] = False

            # BM25 text results → unified pool
            for rank, (idx, _score) in enumerate(bm25_results):
                rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)
                if idx not in rrf_is_table:
                    rrf_is_table[idx] = False

            fused_indices = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:8]

            # --- Phase 3: Build context for LLM ---
            progress_callback("llm", "AI 분석 중...", 70)

            context_parts = []
            all_sources: list[dict] = []
            session_pdf_names = list(session.get("pdfs", {}).keys())
            text_source_idx = 0
            table_source_idx = 0

            for idx in fused_indices:
                is_table = rrf_is_table.get(idx, False)
                chunk_text = bm25_chunks[idx]
                meta = bm25_metadatas[idx] if idx < len(bm25_metadatas) else {}

                if is_table:
                    table_source_idx += 1
                    title = mask_pii_text(meta.get("table_title", "(제목 없음)"))
                    table_id = meta.get("table_id", "")
                    doc_name = meta.get("document_name", "")

                    resolved_pdf_name = doc_name
                    session_table = None
                    for _pn, _pinfo in session.get("pdfs", {}).items():
                        for st in _pinfo.get("tables", []):
                            if st.get("table_id") == table_id or st.get("hybrid_table_id") == table_id:
                                session_table = st
                                resolved_pdf_name = _pn
                                break
                        if session_table:
                            break
                    if not any(p == resolved_pdf_name for p in session_pdf_names):
                        for pn in session_pdf_names:
                            if pn.startswith(doc_name):
                                resolved_pdf_name = pn
                                break

                    merged_html = session_table.get("merged_table_html") if session_table else None
                    if merged_html:
                        try:
                            from pdftablesearch.table_structure_extractor import extract_table_structure as _ets
                            merged_struct = _ets(html=merged_html, table_id=table_id, table_title=title)
                            display_text = mask_pii_text(merged_struct.to_full_text())
                        except Exception:
                            display_text = mask_pii_in_html(merged_html[:1500])
                    else:
                        display_text = mask_pii_text(chunk_text)

                    context_parts.append(f"[표출처{table_source_idx}] 제목: {title}\n{display_text}")

                    bbox_val = meta.get("bounding_box", [0,0,0,0])
                    if bbox_val and all(v == 0 for v in bbox_val):
                        bbox_val = None

                    all_sources.append({
                        "type": "table",
                        "pdf": resolved_pdf_name,
                        "page_number": meta.get("page_number", 1),
                        "text": title,
                        "table_id": table_id,
                        "bounding_box": bbox_val,
                        "merged_table_html": mask_pii_in_html(merged_html) if merged_html else None,
                        "group_id": session_table.get("group_id") if session_table else None,
                        "group_table_ids": session_table.get("group_table_ids") if session_table else None,
                    })
                else:
                    text_source_idx += 1
                    masked_chunk = mask_pii_text(chunk_text)
                    context_parts.append(f"[텍스트출처{text_source_idx}] {masked_chunk}")
                    source_text = mask_pii_text(chunk_text[:500])
                    source_pdf = meta.get("source_pdf", "")
                    if source_pdf and not any(p == source_pdf for p in session_pdf_names):
                        for pn in session_pdf_names:
                            if pn.startswith(source_pdf):
                                source_pdf = pn
                                break
                    all_sources.append({
                        "type": "text",
                        "pdf": source_pdf,
                        "page_number": meta.get("page_number", 1),
                        "text": source_text,
                        "chunk_index": meta.get("chunk_index", 0),
                    })

            context_text = "\n\n---\n\n".join(context_parts)

            system_prompt = (
                "당신은 전문적인 금융 문서 분석 어시스턴트입니다. "
                "아래 [텍스트출처N]과 [표출처N]으로 표시된 문서 내용을 기반으로 질문에 답변하세요.\n\n"
                "규칙:\n"
                "1. 문서에 없는 내용은 추측하지 마세요\n"
                "2. 구체적인 수치, 날짜, 업체명 등을 정확히 인용하세요\n"
                "3. 한국어로 존댓말(~습니다, ~합니다, ~세요)을 사용하여 마크다운 형식으로 답변하세요\n"
                "4. HTML 태그를 사용하지 마세요\n"
                "5. 출처 번호를 [텍스트출처N] 또는 [표출처N] 형식으로 본문에 인용하세요\n"
                "6. 답변 마지막 줄에 '사용출처: 텍스트1,표2' 형식으로 사용한 출처만 표시하세요"
            )

            user_prompt = (
                f"질문: {body.query}\n\n"
                f"참고 문서 내용:\n{context_text[:8000]}\n\n"
                f"답변:"
            )

            # --- Phase 4: LLM streaming ---
            import time as _time
            client = ZaiLLMClient(max_retries=2)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            max_attempts = 5
            accumulated = ""
            for attempt in range(max_attempts):
                try:
                    for chunk in client._llm.stream(messages):
                        token = chunk.content if hasattr(chunk, "content") else str(chunk)
                        if token:
                            accumulated += token
                    break
                except Exception as stream_exc:
                    err_msg = str(stream_exc)
                    if "429" in err_msg and attempt < max_attempts - 1:
                        wait = 15 * (attempt + 1)
                        _time.sleep(wait)
                        accumulated = ""
                        continue
                    raise

            # --- Phase 5: Parse sources and build result ---
            progress_callback("done", "검색 완료!", 100)

            for evt in queue:
                yield evt

            # Parse usage from both 사용출처 line and inline citations
            used_text_indices: list[int] = []
            used_table_indices: list[int] = []
            used_match = re.search(r'사용출처:\s*(.+)', accumulated)
            if used_match:
                for part in used_match.group(1).split(','):
                    part = part.strip().replace('【', '').replace('】', '')
                    if part.startswith('텍스트'):
                        num_str = re.search(r'\d+', part)
                        if num_str:
                            used_text_indices.append(int(num_str.group()) - 1)
                    elif part.startswith('표'):
                        num_str = re.search(r'\d+', part)
                        if num_str:
                            used_table_indices.append(int(num_str.group()) - 1)

            for m in re.finditer(r'[\[【]텍스트출처(\d+)[\]】]', accumulated):
                idx = int(m.group(1)) - 1
                if idx not in used_text_indices:
                    used_text_indices.append(idx)
            for m in re.finditer(r'[\[【]표출처(\d+)[\]】]', accumulated):
                idx = int(m.group(1)) - 1
                if idx not in used_table_indices:
                    used_table_indices.append(idx)

            # Filter sources to only used ones (or all if parsing failed)
            if used_text_indices or used_table_indices:
                text_counter = 0
                table_counter = 0
                filtered_sources = []
                for src in all_sources:
                    if src["type"] == "text":
                        if text_counter in used_text_indices:
                            filtered_sources.append(src)
                        text_counter += 1
                    elif src["type"] == "table":
                        if table_counter in used_table_indices:
                            filtered_sources.append(src)
                        table_counter += 1
            else:
                filtered_sources = all_sources

            # Serialize tables referenced in answer
            referenced_tables = []
            table_sources = [s for s in all_sources if s.get("type") == "table"]
            for ts in table_sources:
                tid = ts.get("table_id", "")
                if not tid:
                    continue
                serialized = {
                    "table_id": tid,
                    "document_name": ts.get("pdf", ""),
                    "page_number": ts.get("page_number", 1),
                    "table_title": ts.get("text", ""),
                    "table_html": "",
                    "table_markdown": "",
                    "relevance_score": None,
                    "bounding_box": ts.get("bounding_box"),
                    "merged_table_html": ts.get("merged_table_html"),
                }
                for _pn, _pinfo in session.get("pdfs", {}).items():
                    for st in _pinfo.get("tables", []):
                        st_tid = st.get("table_id", "")
                        st_hid = st.get("hybrid_table_id", "")
                        if st_tid == tid or st_hid == tid:
                            if st.get("merged_table_html"):
                                serialized["table_html"] = mask_pii_in_html(st["merged_table_html"])
                                serialized["merged_table_html"] = serialized["table_html"]
                            elif st.get("table_html"):
                                serialized["table_html"] = mask_pii_in_html(st["table_html"])
                            else:
                                pass
                            break
                    else:
                        continue
                    break
                else:
                    pass
                referenced_tables.append(serialized)

            result_data = json.dumps({
                "answer": accumulated,
                "tables": referenced_tables,
                "sources": filtered_sources,
            }, ensure_ascii=False)
            yield f"event: result\ndata: {result_data}\n\n"

        except Exception as exc:
            for evt in queue:
                yield evt
            error_data = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/unified-followup")
async def unified_followup_endpoint(
    body: UnifiedFollowupRequest,
    x_session_id: Optional[str] = Header(None),
) -> StreamingResponse:
    session = _get_session(x_session_id)

    # Parse previous sources
    try:
        prev_sources = json.loads(body.sources_json) if body.sources_json else []
    except Exception:
        prev_sources = []

    # Build context from previous answer + sources
    source_texts = []
    for src in prev_sources:
        src_type = "텍스트" if src.get("type") == "text" else "표"
        pdf = src.get("pdf", "")
        page = src.get("page_number", "")
        text = src.get("text", "")
        source_texts.append(f"[{src_type}출처 - {pdf} p.{page}] {mask_pii_text(text)}")

    context_block = "\n\n".join(source_texts)

    system_prompt = (
        "당신은 전문적인 금융 문서 분석 어시스턴트입니다. "
        "이전 검색 결과를 바탕으로 추가 질문에 답변하세요.\n\n"
        "규칙:\n"
        "1. 이전 답변과 출처를 기반으로 답변하세요\n"
        "2. 문서에 없는 내용은 추측하지 마세요\n"
        "3. 한국어로 존댓말(~습니다, ~합니다, ~세요)을 사용하여 마크다운 형식으로 답변하세요\n"
        "4. HTML 태그를 사용하지 마세요"
    )

    user_prompt = (
        f"이전 답변:\n{body.context}\n\n"
        f"이전 출처:\n{context_block}\n\n"
        f"추가 질문: {body.question}\n\n"
        f"답변:"
    )

    def generate():
        try:
            import time as _time
            client = ZaiLLMClient(max_retries=2)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            max_attempts = 5
            accumulated = ""
            for attempt in range(max_attempts):
                try:
                    for chunk in client._llm.stream(messages):
                        token = chunk.content if hasattr(chunk, "content") else str(chunk)
                        if token:
                            accumulated += token
                            data = json.dumps({"token": token}, ensure_ascii=False)
                            yield f"data: {data}\n\n"
                    break
                except Exception as stream_exc:
                    err_msg = str(stream_exc)
                    if "429" in err_msg and attempt < max_attempts - 1:
                        wait = 15 * (attempt + 1)
                        yield f"data: {json.dumps({'token': f'[재시도 중... {wait}초 대기 ({attempt+1}/{max_attempts})]'}, ensure_ascii=False)}\n\n"
                        _time.sleep(wait)
                        accumulated = ""
                        continue
                    raise

            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            data = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


_static_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
if _static_dir.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/",
        StaticFiles(directory=str(_static_dir), html=True),
        name="static",
    )
