"""FastAPI web server for PDFTableSearch React frontend.

Session-based API that replaces the Streamlit app. Each user session gets
its own temporary upload directory and ChromaDB persist directory.

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
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from pdftablesearch import PDFProcessor, PDFTableSearch, smart_search
from pdftablesearch.auth import (
    LDAPUser,
    clear_auth_cookie,
    get_current_user,
    issue_auth_token,
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
from pdftablesearch.vectorstore import TableVectorStore

_sessions: Dict[str, dict] = {}
_embeddings: Optional[SentenceTransformerEmbeddings] = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global _embeddings
    warn_if_insecure_auth_secret()
    # Clean up stale temp directories from previous runs
    import glob as _glob
    import shutil
    for pattern in ["pdf_upload_*", "pdf_chroma_*", "pdf_docchunks_*"]:
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


class LoginRequest(BaseModel):
    username: str
    password: str


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


def get_session_context(
    current_user: LDAPUser = Depends(get_current_user),
    session_id: Optional[str] = Query(default=None),
    x_session_id: Optional[str] = Header(default=None),
) -> SessionContext:
    return _require_owned_session(session_id or x_session_id, current_user)


def _cleanup_session_resources(session: dict[str, Any]) -> None:
    for key in ("upload_dir", "chroma_dir", "doc_chunks_dir"):
        path = session.get(key)
        if path:
            shutil.rmtree(path, ignore_errors=True)


def _create_session_record(owner_id: str, name: str = "") -> tuple[str, dict[str, Any]]:
    session_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    session: Dict[str, Any] = {
        "owner_id": owner_id,
        "upload_dir": tempfile.mkdtemp(prefix="pdf_upload_"),
        "chroma_dir": tempfile.mkdtemp(prefix="pdf_chroma_"),
        "doc_chunks_dir": tempfile.mkdtemp(prefix="pdf_docchunks_"),
        "pdfs": {},
        "searcher": None,
        "name": name,
        "created_at": now,
        "last_activity": now,
        "total_pages": 0,
        "search_count": 0,
        "qa_count": 0,
    }
    _sessions[session_id] = session
    return session_id, session


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


def _classify_table_type(title: Optional[str], html: Optional[str]) -> str:
    text = (title or "") + " " + (html or "")
    text = text.lower()
    if any(k in text for k in ["매출", "재무", "대차대조표", "재무상태표", "자산", "부채", "자본", "현금흐름"]):
        return "재무제표"
    if any(k in text for k in ["손익", "영업이익", "분기별", "매출액", "비용", "수익"]):
        return "손익계산서"
    if any(k in text for k in ["리스크", "위험", "부실", "연체", "부도", "npl", "연체율"]):
        return "리스크"
    if any(k in text for k in ["담보", "보증", "평가", "저당", "근저당", "부동산", "감정"]):
        return "담보"
    return "기타"


def _tokenize_korean(text: str) -> list[str]:
    """Simple tokenizer for Korean + English text."""
    # Split on whitespace and punctuation, keep meaningful tokens
    import re as _re
    tokens = _re.findall(r'[가-힣]+|[a-zA-Z0-9]+', text.lower())
    return tokens


# ---------------------------------------------------------------------------
# Paragraph-based HTML chunker
# ---------------------------------------------------------------------------

_HEADING_TAGS = frozenset(["h1", "h2", "h3", "h4", "h5", "h6", "figcaption"])

_BLOCK_TAGS = frozenset([
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "blockquote", "pre", "div",
])

_PARA_MIN_CHARS = 100
_PARA_MAX_CHARS = 1500


def _extract_blocks_from_html(page_html: str) -> list[str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "html.parser")

    for tag in soup.find_all("table"):
        tag.decompose()

    blocks: list[str] = []

    for child in soup.children:
        if not hasattr(child, "name") or child.name is None:
            text = str(child).strip()
            if text:
                blocks.append(text)
            continue

        tag_name = child.name.lower()

        if tag_name == "table":
            continue

        if tag_name in _BLOCK_TAGS:
            text = child.get_text(separator=" ", strip=True)
            if text:
                blocks.append(text)
        elif tag_name in ("ul", "ol"):
            for li in child.find_all("li", recursive=False):
                text = li.get_text(separator=" ", strip=True)
                if text:
                    blocks.append(text)
        else:
            text = child.get_text(separator=" ", strip=True)
            if text:
                blocks.append(text)

    return blocks


def _extract_blocks_with_headings(page_html: str) -> list[tuple[str, str]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "html.parser")

    for tag in soup.find_all("table"):
        tag.decompose()

    blocks: list[tuple[str, str]] = []
    heading_stack: list[tuple[int, str]] = []

    for child in soup.children:
        if not hasattr(child, "name") or child.name is None:
            text = str(child).strip()
            if text:
                section = " > ".join(h for _, h in heading_stack)
                blocks.append((text, section))
            continue

        tag_name = child.name.lower()

        if tag_name == "table":
            continue

        if tag_name in _HEADING_TAGS:
            heading_text = child.get_text(separator=" ", strip=True)
            if not heading_text:
                continue
            level = int(tag_name[1]) if tag_name[0] == "h" else 3
            heading_stack = [(lv, txt) for lv, txt in heading_stack if lv < level]
            heading_stack.append((level, heading_text))
            section = " > ".join(h for _, h in heading_stack)
            blocks.append((heading_text, section))
            continue

        if tag_name in _BLOCK_TAGS:
            text = child.get_text(separator=" ", strip=True)
            if text:
                section = " > ".join(h for _, h in heading_stack)
                blocks.append((text, section))
        elif tag_name in ("ul", "ol"):
            for li in child.find_all("li", recursive=False):
                text = li.get_text(separator=" ", strip=True)
                if text:
                    section = " > ".join(h for _, h in heading_stack)
                    blocks.append((text, section))
        else:
            text = child.get_text(separator=" ", strip=True)
            if text:
                section = " > ".join(h for _, h in heading_stack)
                blocks.append((text, section))

    return blocks


def _split_long_text(text: str, max_chars: int = _PARA_MAX_CHARS) -> list[str]:
    """Split a single text into pieces at sentence boundaries.

    Tries to split on Korean/English sentence endings (。, ., \n).
    Falls back to word boundaries, then hard cut.
    """
    if len(text) <= max_chars:
        return [text]

    pieces: list[str] = []
    remaining = text

    while len(remaining) > max_chars:
        window = remaining[:max_chars]
        split_pos = -1

        for sep in ["。", ".", "다.", "음.", "임.", "\n", " "]:
            idx = window.rfind(sep)
            if idx > max_chars * 0.3:
                split_pos = idx + len(sep)
                break

        if split_pos <= 0:
            split_pos = max_chars

        pieces.append(remaining[:split_pos].strip())
        remaining = remaining[split_pos:].strip()

    if remaining:
        pieces.append(remaining)

    return pieces


def _split_html_by_paragraphs(
    page_html: str,
    pdf_name: str,
    page_num: int,
) -> list[tuple[str, str, str]]:
    raw_blocks = _extract_blocks_with_headings(page_html)

    if not raw_blocks:
        return []

    merged: list[tuple[str, str]] = []
    for text, section in raw_blocks:
        if merged and len(text) < _PARA_MIN_CHARS:
            merged[-1] = (merged[-1][0] + " " + text, merged[-1][1] or section)
        else:
            merged.append((text, section))

    final_blocks: list[tuple[str, str]] = []
    for text, section in merged:
        for piece in _split_long_text(text):
            final_blocks.append((piece, section))

    result: list[tuple[str, str, str]] = []
    safe_pdf = re.sub(r"[^a-zA-Z0-9가-힣_-]", "_", pdf_name)
    for i, (text, section) in enumerate(final_blocks):
        if not text.strip():
            continue
        para_id = f"{safe_pdf}_p{page_num}_para{i + 1}"
        result.append((text.strip(), para_id, section))

    return result


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


# ---------------------------------------------------------------------------
# Multi-page table detection
# ---------------------------------------------------------------------------

_HEADER_KEYWORDS = frozenset([
    "구분", "구 분", "계정", "주요계정", "연도", "종류", "항목", "구분",
    "분류", "항목", "세목", "유형", "영업년도",
])


def _table_col_count(html: str) -> int:
    m = re.search(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    return len(re.findall(r"<t[dh]", m.group(1))) if m else 0


def _table_first_row(html: str) -> list[str]:
    m = re.search(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    if not m:
        return []
    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(1), re.DOTALL)
    return [re.sub(r"<[^>]+>", "", c).strip() for c in cells]


def _row_has_numbers(row: list[str]) -> bool:
    combined = " ".join(row)
    return bool(re.search(r"[\d,]+\.?\d*", combined))


def _row_has_header_keywords(row: list[str]) -> bool:
    combined = " ".join(row)
    return any(kw in combined for kw in _HEADER_KEYWORDS)


def _enrich_tables_with_pymupdf(pdf_path: str, tables: list[dict]) -> None:
    try:
        import fitz
    except ImportError:
        return

    if not pdf_path or not tables:
        return

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return

    MAX_FITZ_TABLES = 200

    by_page: dict[int, list[dict]] = {}
    for t in tables:
        pn = t.get("page_number", 0)
        by_page.setdefault(pn, []).append(t)

    used_fitz_global: set[tuple[int, int]] = set()

    for pn, page_tables in by_page.items():
        if pn < 1 or pn > len(doc):
            continue

        page = doc[pn - 1]
        page_h = page.rect.height
        page_w = page.rect.width
        fitz_tables = page.find_tables().tables

        fitz_data: list[tuple] = []
        for fi, ft in enumerate(fitz_tables):
            data = ft.extract()
            ft_text = _normalize_text(" ".join(" ".join(str(c or "") for c in row) for row in data))
            fitz_data.append((fi, ft, ft_text))

        matched_fitz: set[int] = set()

        for t in page_tables:
            html_text = _normalize_text(_table_text_content(t.get("table_html", "")))
            if not html_text:
                continue

            best_score = 0.0
            best_fi = -1

            for fi, ft, ft_text in fitz_data:
                score = _table_match_score(html_text, ft_text)
                if score > best_score:
                    best_score = score
                    best_fi = fi

            if best_fi >= 0 and best_score > 0.15:
                matched_fitz.add(best_fi)
                ft = fitz_data[best_fi][1]
                fbbox = list(ft.bbox)
                pdf_bbox = [fbbox[0], page_h - fbbox[3], fbbox[2], page_h - fbbox[1]]

                t["bounding_box"] = [round(v, 2) for v in pdf_bbox]

                y_top_pymupdf = fbbox[1]
                clip = fitz.Rect(0, max(0, y_top_pymupdf - 50), page_w, y_top_pymupdf)
                text_above = page.get_text("text", clip=clip).strip()
                if text_above and len(text_above) <= 150:
                    last_line = text_above.split("\n")[-1].strip()
                    if last_line and len(last_line) <= 80:
                        if not t.get("table_title"):
                            t["table_title"] = last_line

                print(f"[enrich] {t.get('table_id')} p{pn}: matched fitz_t[{best_fi}] score={best_score:.2f}")

        for fi, ft, ft_text in fitz_data:
            if fi in matched_fitz:
                continue
            fbbox = list(ft.bbox)
            fbbox_area = (fbbox[2] - fbbox[0]) * (fbbox[3] - fbbox[1])
            if fbbox_area < 5000:
                continue

            is_inner = False
            for fi2, ft2, _ in fitz_data:
                if fi2 == fi:
                    continue
                obbox = list(ft2.bbox)
                if (obbox[0] <= fbbox[0] and obbox[1] <= fbbox[1]
                        and obbox[2] >= fbbox[2] and obbox[3] >= fbbox[3]):
                    is_inner = True
                    break
            if is_inner:
                continue

            pdf_bbox = [fbbox[0], page_h - fbbox[3], fbbox[2], page_h - fbbox[1]]
            data = ft.extract()
            if not data:
                continue

            from bs4 import BeautifulSoup
            html_parts = ["<table>"]
            for ri, row in enumerate(data):
                tag = "th" if ri == 0 else "td"
                html_parts.append("<tr>" + "".join(f"<{tag}>{_escape_html(str(c or ''))}</{tag}>" for c in row) + "</tr>")
            html_parts.append("</table>")
            table_html = "".join(html_parts)

            table_title = ""
            y_top_pymupdf = fbbox[1]
            clip = fitz.Rect(0, max(0, y_top_pymupdf - 50), page_w, y_top_pymupdf)
            text_above = page.get_text("text", clip=clip).strip()
            if text_above and len(text_above) <= 150:
                last_line = text_above.split("\n")[-1].strip()
                if last_line and len(last_line) <= 80:
                    table_title = last_line

            new_id = f"table_{pn}_fitz{fi}"
            new_table = {
                "table_id": new_id,
                "page_number": pn,
                "bounding_box": [round(v, 2) for v in pdf_bbox],
                "table_html": table_html,
                "table_title": table_title or None,
                "document_name": tables[0].get("document_name", "") if tables else "",
            }
            tables.append(new_table)
            print(f"[enrich] ADDED {new_id} p{pn}: bbox={new_table['bounding_box']} (PyMuPDF only, outer)")

        if len(tables) > MAX_FITZ_TABLES:
            print(f"[enrich] WARNING: too many tables ({len(tables)}), stopping PyMuPDF additions")
            break

    doc.close()


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _normalize_text(text: str) -> str:
    import re
    text = text.lower()
    text = re.sub(r'\s+', '', text)
    return text


def _table_text_content(html: str) -> str:
    from bs4 import BeautifulSoup
    try:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator=" ", strip=True)
    except Exception:
        return ""


def _table_match_score(html_norm: str, fitz_norm: str) -> float:
    if not html_norm or not fitz_norm:
        return 0.0
    if fitz_norm in html_norm:
        return 0.9
    if html_norm in fitz_norm:
        return 0.9
    html_words = set(html_norm)
    fitz_words = set(fitz_norm)
    if not html_words or not fitz_words:
        return 0.0
    intersection = html_words & fitz_words
    union = html_words | fitz_words
    return len(intersection) / len(union)


def _extract_top_level_tables_with_nesting(html_path: str) -> list[dict]:
    from bs4 import BeautifulSoup
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []

    soup = BeautifulSoup(content, "html.parser")
    result = []
    for table_tag in soup.find_all("table"):
        parent = table_tag.parent
        is_nested = False
        p = parent
        while p:
            if p.name == "td":
                pp = p.parent
                while pp:
                    if pp.name == "table" and pp != table_tag:
                        is_nested = True
                        break
                    pp = pp.parent
                if is_nested:
                    break
            p = p.parent
        if is_nested:
            continue

        has_inner = bool(table_tag.find("table"))
        text = _normalize_text(table_tag.get_text(separator=" ", strip=True))
        result.append({
            "html": str(table_tag),
            "text": text,
            "has_nested_table": has_inner,
        })
    return result


def _build_tables_from_pymupdf(
    pdf_path: str,
    hybrid_tables: list[dict],
    standard_html_path: str | None,
) -> list[dict]:
    try:
        import fitz
    except ImportError:
        return hybrid_tables

    if not pdf_path:
        return hybrid_tables

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return hybrid_tables

    doc_name = hybrid_tables[0].get("document_name", "") if hybrid_tables else ""

    standard_tables: list[dict] = []
    if standard_html_path:
        standard_tables = _extract_top_level_tables_with_nesting(standard_html_path)
    print(f"[build] standard HTML tables: {len(standard_tables)} (nested marked)")

    hybrid_by_page: dict[int, list[dict]] = {}
    for t in hybrid_tables:
        pn = t.get("page_number", 0)
        hybrid_by_page.setdefault(pn, []).append(t)

    all_fitz: list[dict] = []
    for page_idx in range(len(doc)):
        pn = page_idx + 1
        page = doc[page_idx]
        page_h = page.rect.height
        page_w = page.rect.width
        fitz_tables = page.find_tables().tables

        fitz_data = []
        for fi, ft in enumerate(fitz_tables):
            fbbox = list(ft.bbox)
            area = (fbbox[2] - fbbox[0]) * (fbbox[3] - fbbox[1])
            if area < 5000:
                continue
            data = ft.extract()
            ft_text = _normalize_text(" ".join(" ".join(str(c or "") for c in row) for row in data))
            pdf_bbox = [fbbox[0], page_h - fbbox[3], fbbox[2], page_h - fbbox[1]]
            fitz_data.append({
                "fi": fi, "ft": ft, "bbox": fbbox, "pdf_bbox": pdf_bbox,
                "area": area, "text": ft_text, "data": data, "page": pn,
            })

        inner_indices = set()
        for i, fd in enumerate(fitz_data):
            for j, fd2 in enumerate(fitz_data):
                if i == j:
                    continue
                b1, b2 = fd["bbox"], fd2["bbox"]
                if (b2[0] <= b1[0] and b2[1] <= b1[1] and b2[2] >= b1[2] and b2[3] >= b1[3]):
                    inner_indices.add(i)

        for i, fd in enumerate(fitz_data):
            fd["is_inner"] = i in inner_indices
            all_fitz.append(fd)

    outer_fitz = [f for f in all_fitz if not f["is_inner"]]
    inner_fitz = [f for f in all_fitz if f["is_inner"]]

    for o in outer_fitz:
        o["inner_table_indices"] = []
    for idx, inn in enumerate(inner_fitz):
        for oi, o in enumerate(outer_fitz):
            ob = o["bbox"]
            ib = inn["bbox"]
            if (ob[0] <= ib[0] and ob[1] <= ib[1] and ob[2] >= ib[2] and ob[3] >= ib[3]
                    and o["page"] == inn["page"]):
                o["inner_table_indices"].append(idx)
                break

    results: list[dict] = []
    matched_hybrid_ids: set[str] = set()
    matched_standard: set[int] = set()

    for oi, o in enumerate(outer_fitz):
        has_inner = len(o["inner_table_indices"]) > 0
        table_html = ""
        source = "none"
        hybrid_bbox: list = []
        hybrid_title = ""

        if has_inner and standard_tables:
            best_score = 0.0
            best_si = -1
            for si, st in enumerate(standard_tables):
                if not st["has_nested_table"]:
                    continue
                if si in matched_standard:
                    continue
                score = _table_match_score(o["text"], st["text"])
                if score > best_score:
                    best_score = score
                    best_si = si
            if best_si >= 0 and best_score > 0.10:
                table_html = standard_tables[best_si]["html"]
                matched_standard.add(best_si)
                source = "standard"
                print(f"[build] outer p{o['page']} fitz[{o['fi']}] → standard[{best_si}] score={best_score:.2f} (nested)")

        if not table_html:
            best_score = 0.0
            best_ht = None
            page_hybrid = hybrid_by_page.get(o["page"], [])
            for ht in page_hybrid:
                if ht.get("table_id", "") in matched_hybrid_ids:
                    continue
                ht_bbox = ht.get("bounding_box", [])
                if not ht_bbox or ht_bbox == [0, 0, 0, 0]:
                    continue
                html_text = _normalize_text(_table_text_content(ht.get("table_html", "")))
                text_score = _table_match_score(html_text, o["text"])
                score = text_score
                ya1, ya2 = o["pdf_bbox"][1], o["pdf_bbox"][3]
                yb1, yb2 = ht_bbox[1], ht_bbox[3]
                overlap_start = max(ya1, yb1)
                overlap_end = min(ya2, yb2)
                if overlap_start < overlap_end:
                    y_overlap = (overlap_end - overlap_start) / max(min(ya2 - ya1, yb2 - yb1), 1)
                    score = text_score * (0.5 + 0.5 * y_overlap)
                else:
                    score = text_score * 0.1
                if score > best_score:
                    best_score = score
                    best_ht = ht
            if best_ht and best_score > 0.10:
                table_html = best_ht.get("table_html", "")
                matched_hybrid_ids.add(best_ht.get("table_id", ""))
                hybrid_bbox = best_ht.get("bounding_box", [])
                hybrid_title = best_ht.get("table_title", "")
                source = "hybrid"
                print(f"[build] outer p{o['page']} fitz[{o['fi']}] → hybrid score={best_score:.2f}")

        if not table_html:
            data = o.get("data", [])
            if data:
                html_parts = ["<table>"]
                for ri, row in enumerate(data):
                    tag = "th" if ri == 0 else "td"
                    html_parts.append("<tr>" + "".join(f"<{tag}>{_escape_html(str(c or ''))}</{tag}>" for c in row) + "</tr>")
                html_parts.append("</table>")
                table_html = "".join(html_parts)
                source = "pymupdf"
                print(f"[build] outer p{o['page']} fitz[{o['fi']}] → pymupdf fallback")

        title = hybrid_title or ""
        if not title:
            try:
                title_page = doc[o["page"] - 1]
                y_top = o["bbox"][1]
                clip = fitz.Rect(0, max(0, y_top - 50), title_page.rect.width, y_top)
                text_above = title_page.get_text("text", clip=clip).strip()
                if text_above and len(text_above) <= 150:
                    last_line = text_above.split("\n")[-1].strip()
                    if last_line and len(last_line) <= 80:
                        title = last_line
            except Exception:
                pass

        inner_ids = []
        for inner_idx in o.get("inner_table_indices", []):
            inner_ids.append(f"fitz_p{inner_fitz[inner_idx]['page']}_{inner_fitz[inner_idx]['fi']}_inner")

        final_bbox = [round(v, 2) for v in o["pdf_bbox"]]

        results.append({
            "table_id": f"fitz_p{o['page']}_{o['fi']}",
            "page_number": o["page"],
            "bounding_box": final_bbox,
            "table_html": table_html,
            "table_title": title or None,
            "document_name": doc_name,
            "has_inner_tables": has_inner,
            "is_inner": False,
            "outer_table_id": None,
            "inner_table_ids": inner_ids,
            "_source": source,
        })

    doc.close()

    for pn, page_tables in hybrid_by_page.items():
        for ht in page_tables:
            ht_id = ht.get("table_id", "")
            if ht_id in matched_hybrid_ids:
                continue
            ht_copy = dict(ht)
            ht_copy["_source"] = "hybrid_fallback"
            ht_bbox = ht_copy.get("bounding_box", [])
            is_inner_hybrid = False
            if ht_bbox and len(ht_bbox) >= 4 and ht_bbox != [0, 0, 0, 0]:
                for r in results:
                    r_bbox = r.get("bounding_box", [])
                    if (r.get("page_number") == pn and r_bbox and len(r_bbox) >= 4
                            and r_bbox[0] <= ht_bbox[0] and r_bbox[1] <= ht_bbox[1]
                            and r_bbox[2] >= ht_bbox[2] and r_bbox[3] >= ht_bbox[3]):
                        is_inner_hybrid = True
                        break
            if is_inner_hybrid:
                print(f"[build] skip p{pn}: {ht_id} (inner of existing fitz table)")
                continue
            results.append(ht_copy)
            print(f"[build] fallback p{pn}: {ht_id} (no PyMuPDF match, using hybrid)" +
                   (" [inner]" if ht_copy.get("is_inner") else ""))

    print(f"[build] RESULT: {len(results)} outer tables "
          f"(standard={sum(1 for r in results if r['_source']=='standard')}, "
          f"hybrid={sum(1 for r in results if r['_source']=='hybrid')}, "
          f"pymupdf={sum(1 for r in results if r['_source']=='pymupdf')}, "
          f"hybrid_fallback={sum(1 for r in results if r['_source']=='hybrid_fallback')})")
    return results


def _detect_multipage_tables(
    tables: list[dict],
) -> list[dict]:
    outer_tables = [t for t in tables if not t.get("is_inner") and t.get("_source") != "hybrid_fallback"]

    by_page: dict[int, list[dict]] = {}
    for t in outer_tables:
        pn = t.get("page_number", -1)
        by_page.setdefault(pn, []).append(t)

    sorted_pages = sorted(by_page.keys())

    for pa in sorted_pages:
        for t in by_page[pa]:
            print(f"[multipage] table={t.get('table_id')} page={pa} bbox={t.get('bounding_box')}")

    raw_pairs: list[tuple[str, str, bool]] = []

    for pi in range(len(sorted_pages) - 1):
        pa, pb = sorted_pages[pi], sorted_pages[pi + 1]
        if pb != pa + 1:
            continue

        tables_a = by_page.get(pa, [])
        tables_b = by_page.get(pb, [])
        if not tables_a or not tables_b:
            continue

        last_on_a = None
        last_bbox = [0, 9999, 0, 0]
        for t in tables_a:
            bbox = t.get("bounding_box", [0, 0, 0, 0])
            if len(bbox) >= 4 and bbox != [0, 0, 0, 0] and bbox[1] < last_bbox[1]:
                last_on_a = t
                last_bbox = bbox

        first_on_b = None
        first_bbox = [0, 0, 0, 0]
        for t in tables_b:
            bbox = t.get("bounding_box", [0, 0, 0, 0])
            if len(bbox) >= 4 and bbox != [0, 0, 0, 0] and bbox[3] > first_bbox[3]:
                first_on_b = t
                first_bbox = bbox

        if not (last_on_a and first_on_b):
            continue

        bbox_a = last_on_a.get("bounding_box", [0, 0, 0, 0])
        bbox_b = first_on_b.get("bounding_box", [0, 0, 0, 0])
        if len(bbox_a) < 4 or len(bbox_b) < 4:
            continue

        a_near_bottom = bbox_a[1] < 200
        b_near_top = bbox_b[3] > 400

        if not (a_near_bottom and b_near_top):
            print(f"[multipage] p{pa}→p{pb}: pos check failed, a_bottom={bbox_a[1]:.0f}({'✓' if a_near_bottom else '✗'}), b_top={bbox_b[3]:.0f}({'✓' if b_near_top else '✗'})")
            continue

        html_a = last_on_a.get("table_html", "") or last_on_a.get("html", "")
        html_b = first_on_b.get("table_html", "") or first_on_b.get("html", "")
        if not html_a or not html_b:
            continue

        cols_a = _table_col_count(html_a)
        cols_b = _table_col_count(html_b)
        same_cols = cols_a == cols_b and cols_a > 0
        table_at_very_top = bbox_b[3] > 700
        force_include = not same_cols and table_at_very_top

        if not same_cols and not force_include:
            print(f"[multipage] {last_on_a['table_id']}@p{pa}(cols={cols_a}) -> {first_on_b['table_id']}@p{pb}(cols={cols_b}) skipped (different cols)")
            continue

        raw_pairs.append((last_on_a["table_id"], first_on_b["table_id"], same_cols))
        tag = "paired" if same_cols else "paired (cols differ, table at very top)"
        print(f"[multipage] {last_on_a['table_id']}@p{pa}(cols={cols_a}) -> {first_on_b['table_id']}@p{pb}(cols={cols_b}) {tag}")

    # Transitive closure: A→B, B→C => chain [A, B, C]
    chains: list[list[str]] = []
    table_to_chain: dict[str, int] = {}

    for aid, bid, _ in raw_pairs:
        a_chain = table_to_chain.get(aid)
        b_chain = table_to_chain.get(bid)

        if a_chain is not None and b_chain is not None:
            if a_chain == b_chain:
                continue
            src, dst = (b_chain, a_chain) if len(chains[a_chain]) >= len(chains[b_chain]) else (a_chain, b_chain)
            for tid in chains[src]:
                table_to_chain[tid] = dst
            chains[dst].extend(chains[src])
            chains[src] = []
        elif a_chain is not None:
            chains[a_chain].append(bid)
            table_to_chain[bid] = a_chain
        elif b_chain is not None:
            chains[b_chain].insert(0, aid)
            table_to_chain[aid] = b_chain
        else:
            idx = len(chains)
            chains.append([aid, bid])
            table_to_chain[aid] = idx
            table_to_chain[bid] = idx

    chains = [c for c in chains if len(c) >= 2]

    by_id = {t["table_id"]: t for t in tables}

    results: list[dict] = []
    for ci, chain in enumerate(chains):
        gid = f"group_{ci}"

        pair_cols: list[tuple[bool, int, int]] = []
        for i in range(len(chain) - 1):
            ta = by_id.get(chain[i], {})
            tb = by_id.get(chain[i + 1], {})
            html_a = ta.get("table_html", "") or ta.get("html", "")
            html_b = tb.get("table_html", "") or tb.get("html", "")
            cols_a = _table_col_count(html_a) if html_a else 0
            cols_b = _table_col_count(html_b) if html_b else 0
            pair_cols.append((cols_a == cols_b and cols_a > 0, cols_a, cols_b))

        all_same = all(sc for sc, _, _ in pair_cols)

        tables_info = []
        for tid in chain:
            t = by_id.get(tid, {})
            tables_info.append({
                "table_id": tid,
                "page_number": t.get("page_number"),
                "bounding_box": t.get("bounding_box", []),
                "table_title": t.get("table_title"),
                "table_html": t.get("table_html", ""),
            })

        results.append({
            "group_id": gid,
            "tables": tables_info,
            "chain_length": len(chain),
            "same_cols": all_same,
            "pair_cols": pair_cols,
        })

        print(f"[multipage] chain {gid}: {' -> '.join(chain)} (all_same_cols={all_same})")

    print(f"[multipage] RESULT: {len(raw_pairs)} pairs -> {len(chains)} chains")
    return results


def _apply_table_groups(
    session: dict, pdf_name: str, tier1: list[tuple[str, str, str]],
    tier2_confirmed: list[tuple[str, str, str]],
) -> None:
    tables = session["pdfs"][pdf_name].get("tables", [])
    by_id = {t["table_id"]: t for t in tables}

    for pairs in (tier1, tier2_confirmed):
        for aid, bid, gid in pairs:
            if aid in by_id:
                by_id[aid]["group_id"] = gid
            if bid in by_id:
                by_id[bid]["group_id"] = gid


def _merge_grouped_tables(tables: list[dict]) -> None:
    from bs4 import BeautifulSoup

    groups: dict[str, list[dict]] = {}
    for t in tables:
        gid = t.get("group_id")
        if gid:
            groups.setdefault(gid, []).append(t)

    for gid, group_tables in groups.items():
        if len(group_tables) < 2:
            continue

        group_table_ids = [t["table_id"] for t in group_tables]

        soup_a = BeautifulSoup(group_tables[0].get("table_html", ""), "html.parser")
        table_a = soup_a.find("table")
        if not table_a:
            continue

        first_header_texts: list[str] = []
        first_row_a = table_a.find("tr")
        if first_row_a:
            first_header_texts = [c.get_text(strip=True) for c in first_row_a.find_all(["td", "th"])]

        for tb in group_tables[1:]:
            soup_b = BeautifulSoup(tb.get("table_html", ""), "html.parser")
            table_b = soup_b.find("table")
            if not table_b:
                continue

            rows_b = table_b.find_all("tr")
            cols_a = len(first_row_a.find_all(["td", "th"])) if first_row_a else 0

            for row in rows_b:
                cells = row.find_all(["td", "th"])
                if cols_a > 0 and len(cells) == cols_a:
                    row_texts = [c.get_text(strip=True) for c in cells]
                    if row_texts == first_header_texts:
                        continue
                table_a.append(row)

        merged_html = str(soup_a)

        for t in group_tables:
            t["merged_table_html"] = merged_html
            t["group_table_ids"] = group_table_ids


class ConfirmGroupRequest(BaseModel):
    pdf_name: str
    confirmed: list[dict]
    rejected: list[dict]


@app.post("/api/auth/login")
async def login(body: LoginRequest, response: Response) -> dict[str, Any]:
    try:
        client = ldap_client_from_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    user = client.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid LDAP credentials")

    token, ttl_seconds = issue_auth_token(user)
    set_auth_cookie(response, token, ttl_seconds)
    return {"user": user.model_dump()}


@app.post("/api/auth/logout")
async def logout(response: Response) -> dict[str, bool]:
    clear_auth_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(current_user: LDAPUser = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": current_user.model_dump()}


@app.post("/api/confirm-table-groups")
async def confirm_table_groups(
    body: ConfirmGroupRequest,
    session_ctx: SessionContext = Depends(get_session_context),
) -> JSONResponse:
    session = session_ctx.session
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
async def list_sessions(current_user: LDAPUser = Depends(get_current_user)) -> JSONResponse:
    sessions = [
        _serialize_session_brief(sid, s)
        for sid, s in _sessions.items()
        if s.get("owner_id") == current_user.user_id
    ]
    return JSONResponse(content={"sessions": sessions, "total": len(sessions)})


@app.post("/api/sessions")
async def create_session(
    body: CreateSessionRequest,
    current_user: LDAPUser = Depends(get_current_user),
) -> JSONResponse:
    session_id, session = _create_session_record(
        owner_id=current_user.user_id,
        name=body.name or "",
    )
    return JSONResponse(
        content={"session_id": session_id, "name": session["name"]},
        status_code=201,
    )


@app.get("/api/sessions/{session_id}")
async def get_session(
    session_id: str,
    current_user: LDAPUser = Depends(get_current_user),
) -> JSONResponse:
    session_ctx = _require_owned_session(session_id, current_user)
    return JSONResponse(content=_serialize_session_brief(session_id, session_ctx.session))


@app.put("/api/sessions/{session_id}")
async def update_session(
    session_id: str,
    body: UpdateSessionRequest,
    current_user: LDAPUser = Depends(get_current_user),
) -> JSONResponse:
    session_ctx = _require_owned_session(session_id, current_user)
    session = session_ctx.session
    session["name"] = body.name
    session["last_activity"] = datetime.now(timezone.utc).isoformat()
    return JSONResponse(content=_serialize_session_brief(session_id, session))


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: LDAPUser = Depends(get_current_user),
) -> JSONResponse:
    session_ctx = _require_owned_session(session_id, current_user)
    session = _sessions.pop(session_id)
    _cleanup_session_resources(session_ctx.session)
    return JSONResponse(content={"deleted": session_id})


@app.get("/api/documents/pdf")
async def get_document_pdf(
    name: str,
    session_ctx: SessionContext = Depends(get_session_context),
):
    from starlette.responses import FileResponse
    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
):
    """Render a specific PDF page as a PNG image using PyMuPDF."""
    from starlette.responses import Response
    import fitz

    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
):
    import re
    from starlette.responses import Response
    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
):
    from starlette.responses import Response
    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
):
    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> HTMLResponse:
    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> HTMLResponse:
    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> JSONResponse:
    """Extract images from PDF's HTML with surrounding context text.

    Converts the PDF with ``image_output="embedded"`` if not already done,
    then parses the HTML to find all ``<img>`` tags with their alt text,
    preceding/following text context, and page number.
    """
    session = session_ctx.session
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
    current_user: LDAPUser = Depends(get_current_user),
) -> JSONResponse:
    session_id: str
    session: Dict[str, Any]
    now = datetime.now(timezone.utc).isoformat()

    if x_session_id:
        session_ctx = _require_owned_session(x_session_id, current_user)
        session_id = session_ctx.session_id
        session = session_ctx.session
    else:
        session_id, session = _create_session_record(owner_id=current_user.user_id)

    upload_dir = session["upload_dir"]
    chroma_dir = session["chroma_dir"]

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
        if pymupdf_only_count:
            print(f"[index] Added {pymupdf_only_count} PyMuPDF-only tables to ChromaDB for {filename}")

        session["pdfs"][filename] = {
            "path": str(dest),
            "upload_dir": upload_dir,
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
            persist_dir=chroma_dir,
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
async def list_pdfs(session_ctx: SessionContext = Depends(get_session_context)) -> JSONResponse:
    session = session_ctx.session

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
    session_ctx: SessionContext = Depends(get_session_context),
) -> JSONResponse:
    session = session_ctx.session

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
    session_ctx: SessionContext = Depends(get_session_context),
) -> JSONResponse:
    session = session_ctx.session
    session["search_count"] = session.get("search_count", 0) + 1
    start = time.time()

    chroma_dir = session["chroma_dir"]
    if not session["pdfs"]:
        return JSONResponse(
            content={"results": [], "total": 0, "time_seconds": 0.0}
        )

    try:
        embeddings = _get_embeddings()
        vector_store = TableVectorStore(
            embeddings=embeddings,
            persist_dir=chroma_dir,
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> StreamingResponse:
    session = session_ctx.session
    session["search_count"] = session.get("search_count", 0) + 1

    pdf_name = body.pdf_name
    if pdf_name and pdf_name in session["pdfs"]:
        pdf_path = session["pdfs"][pdf_name]["path"]
    else:
        if not session["pdfs"]:
            raise HTTPException(status_code=400, detail="No PDFs uploaded in this session")
        first_pdf = next(iter(session["pdfs"].values()))
        pdf_path = first_pdf["path"]

    chroma_dir = session["chroma_dir"]
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
                persist_dir=chroma_dir,
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> StreamingResponse:
    session = session_ctx.session
    session["qa_count"] = session.get("qa_count", 0) + 1

    import hashlib
    table_id_key = body.table_title or hashlib.md5(body.table_html[:200].encode()).hexdigest()
    qa_key = hashlib.md5(f"{table_id_key}:{body.question}".encode()).hexdigest()

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
    session_ctx: SessionContext = Depends(get_session_context),
) -> JSONResponse:
    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> JSONResponse:
    session = session_ctx.session
    html = _find_table_html(session, table_id)
    transposed_html = _transpose_table_html(html)
    return JSONResponse(content={"html": transposed_html})


@app.post("/api/table-calculate")
async def table_calculate(
    body: CalculateRequest,
    session_ctx: SessionContext = Depends(get_session_context),
) -> StreamingResponse:
    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> StreamingResponse:
    session = session_ctx.session
    session_id = session_ctx.session_id
    session["qa_count"] = session.get("qa_count", 0) + 1

    if not session.get("document_chunks_ready"):
        _chunk_and_index_session(session_id)

    embeddings = _get_embeddings()

    vector_store = TableVectorStore(
        embeddings=embeddings,
        persist_dir=session["doc_chunks_dir"],
        collection_name=f"doc_chunks_{session_id}",
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> StreamingResponse:
    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> HTMLResponse:
    session = session_ctx.session
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> StreamingResponse:
    """Translate PDF text to target language, streaming each chunk via SSE.

    SSE events:
        ``chunk_done`` — ``{"chunk", "total_chunks", "translated_text"}`
        ``done``       — ``{"total_chunks", "full_text"}`
        ``error``      — ``{"error"}`
    """
    session = session_ctx.session
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
async def translate_status(
    job_id: str,
    current_user: LDAPUser = Depends(get_current_user),
) -> JSONResponse:
    # Kept for backward compatibility — returns a stub response.
    return JSONResponse(content={"status": "deprecated"})


@app.get("/api/translate/result/{job_id}")
async def translate_html_file(
    job_id: str,
    current_user: LDAPUser = Depends(get_current_user),
) -> JSONResponse:
    # Kept for backward compatibility — returns a stub response.
    return JSONResponse(content={"status": "deprecated"})


# ---------------------------------------------------------------------------
# Unified Search (문서 검색) — combines table + text search
# ---------------------------------------------------------------------------


@app.post("/api/unified-search")
async def unified_search_endpoint(
    body: UnifiedSearchRequest,
    session_ctx: SessionContext = Depends(get_session_context),
) -> StreamingResponse:
    session = session_ctx.session
    session_id = session_ctx.session_id

    # Ensure text chunks are indexed
    if not session.get("document_chunks_ready"):
        _chunk_and_index_session(session_id)

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
                persist_dir=session["chroma_dir"],
            )
            table_results = table_store.similarity_search(query=body.query, k=15)

            # --- Phase 2: Hybrid search on doc_chunks ---
            progress_callback("text", "텍스트 검색 중...", 40)
            doc_store = TableVectorStore(
                embeddings=embeddings,
                persist_dir=session["doc_chunks_dir"],
                collection_name=f"doc_chunks_{session_id}",
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
                            if st.get("table_id") == table_id:
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
                        if st.get("table_id") == tid:
                            if st.get("merged_table_html"):
                                serialized["table_html"] = mask_pii_in_html(st["merged_table_html"])
                                serialized["merged_table_html"] = serialized["table_html"]
                            elif st.get("table_html"):
                                serialized["table_html"] = mask_pii_in_html(st["table_html"])
                            break
                    else:
                        continue
                    break
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
    session_ctx: SessionContext = Depends(get_session_context),
) -> StreamingResponse:
    session = session_ctx.session

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
