"""PDFTableSearch FastAPI REST API 서버.

PDF 업로드, 표 검색, 표 내용 질의응답을 위한 HTTP 엔드포인트를 제공한다.

실행::

    uvicorn pdftablesearch.api:app --host 0.0.0.0 --port 8000

엔드포인트:
    POST /search      - 업로드된 PDF에서 표 검색
    POST /ask         - PDF 표에 대한 질의응답
    GET  /health      - 상태 확인
"""

from __future__ import annotations

import tempfile
import shutil
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="PDFTableSearch API",
    version="0.1.0",
)

_upload_dir = tempfile.mkdtemp(prefix="pdftablesearch_api_")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/search")
async def search(
    files: List[UploadFile] = File(...),
    query: str = Form(...),
    max_results: int = Form(5),
) -> dict:
    """업로드된 PDF 파일에서 표를 검색한다."""
    from pdftablesearch.core import search_tables

    pdf_paths: List[str] = []
    for upload in files:
        if not upload.filename or not upload.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"Only PDF files accepted: {upload.filename}")
        dest = f"{_upload_dir}/{upload.filename}"
        with open(dest, "wb") as f:
            content = await upload.read()
            f.write(content)
        pdf_paths.append(dest)

    if not pdf_paths:
        raise HTTPException(400, "No PDF files provided")

    try:
        if len(pdf_paths) == 1:
            results = search_tables(pdf_paths[0], query, max_results=max_results)
            return {
                "query": query,
                "total": len(results),
                "results": [r.to_dict() for r in results],
            }
        else:
            result = search_tables(pdf_paths, query, max_results=max_results)
            return result.to_dict()
    except Exception as exc:
        logger.error("Search failed: %s", exc)
        raise HTTPException(500, str(exc)) from exc


@app.post("/ask")
async def ask(
    file: UploadFile = File(...),
    query: str = Form(...),
) -> dict:
    """업로드된 PDF의 표에 대해 질문한다."""
    from pdftablesearch.table_qa import ask_table

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted")

    dest = f"{_upload_dir}/{file.filename}"
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        answer = ask_table(query=query, pdf_path=dest)
        return {"query": query, "answer": answer}
    except Exception as exc:
        logger.error("QA failed: %s", exc)
        raise HTTPException(500, str(exc)) from exc


@app.on_event("shutdown")
async def shutdown() -> None:
    shutil.rmtree(_upload_dir, ignore_errors=True)
