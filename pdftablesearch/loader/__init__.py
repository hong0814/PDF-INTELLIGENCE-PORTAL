"""opendataloader-pdf 기반 PDF 문서 로딩 (HTML 우선 방식).

:class:`PDFProcessor` 클래스와 PDF→문서 변환 지원 함수를 제공한다.
하위 모듈에 구현이 분산되어 있으나, 모든 공개 심볼은 하위 호환을 위해
여기서 재export된다.

하위 모듈:
    html_parser: HTML 표 추출, 정제, HTML→Markdown 변환.
    json_parser: opendataloader-pdf JSON 출력에서 메타데이터 파싱.
    markdown_parser: Markdown 표 추출 및 제목/컨텍스트 파싱.
    matcher: 콘텐츠 기반 HTML↔JSON 표 매칭 (Jaccard 유사도).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz
import opendataloader_pdf
from langchain_core.documents import Document

from pdftablesearch.exceptions import PDFProcessingError, TableParsingError
from pdftablesearch.models import ProcessingResult
from pdftablesearch.utils import get_logger, validate_pdf_path

from pdftablesearch.loader.html_parser import (
    extract_html_tables_from_file,
    extract_table_text_content,
    html_table_to_markdown,
    sanitize_table_html,
)
from pdftablesearch.loader.json_parser import (
    parse_json_metadata,
    reconstruct_table_markdown,
)
from pdftablesearch.loader.markdown_parser import (
    extract_markdown_tables,
    extract_markdown_tables_from_file,
    extract_table_info,
)
from pdftablesearch.loader.matcher import (
    find_best_json_match,
)
from pdftablesearch.table_structure_extractor import extract_table_structure

logger = get_logger(__name__)

# Re-export regex constants for backward compatibility
import re
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR_RE = re.compile(r"^\s*\|[-:]+\|.*\|[-:]+\|?\s*$")


class PDFProcessor:
    """opendataloader-pdf 기반 PDF 문서 처리 클래스 (HTML 우선 방식)."""

    def __init__(
        self,
        parallel_workers: int = 4,
        output_dir: Optional[str] = None,
    ) -> None:
        self.parallel_workers = parallel_workers
        self._output_dir = output_dir

    def _get_output_dir(self, pdf_path: Path) -> Path:
        if self._output_dir:
            return Path(self._output_dir)
        return Path(tempfile.mkdtemp(prefix="pdftablesearch_"))

    def convert_pdf(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        use_hybrid: bool = True,
    ) -> Path:
        """opendataloader-pdf를 사용하여 PDF를 Markdown + JSON으로 변환한다."""
        validated_path = Path(pdf_path)
        target_dir = Path(output_dir) if output_dir else self._get_output_dir(validated_path)
        target_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Converting PDF: %s -> %s (hybrid=%s)", validated_path, target_dir, use_hybrid)

        try:
            convert_params = {
                "input_path": str(validated_path),
                "output_dir": str(target_dir),
                "format": "html, json, markdown",
                "html_page_separator": "<div class='page-sep' data-pn='%page-number%'></div>",
            }
            if use_hybrid:
                convert_params["hybrid"] = "docling-fast"
                convert_params["hybrid_url"] = "http://localhost:5002"
                try:
                    opendataloader_pdf.convert(**convert_params)
                except TypeError:
                    # html_page_separator may not be supported in older versions
                    convert_params.pop("html_page_separator", None)
                    try:
                        opendataloader_pdf.convert(**convert_params)
                    except TypeError:
                        convert_params.pop("hybrid")
                        convert_params.pop("hybrid_url")
                        opendataloader_pdf.convert(**convert_params)
                except Exception:
                    logger.warning("Hybrid conversion failed, falling back to standard conversion")
                    convert_params.pop("hybrid")
                    convert_params.pop("hybrid_url")
                    opendataloader_pdf.convert(**convert_params)
            else:
                try:
                    opendataloader_pdf.convert(**convert_params)
                except TypeError:
                    convert_params.pop("html_page_separator", None)
                    opendataloader_pdf.convert(**convert_params)
        except Exception as exc:
            raise PDFProcessingError(
                f"opendataloader-pdf conversion failed for {validated_path}",
                details={"path": str(validated_path), "error": str(exc)},
            ) from exc

        return target_dir

    def load_documents(
        self,
        pdf_path: str,
        force_reload: bool = False,
        output_dir: Optional[str] = None,
        use_hybrid: bool = True,
    ) -> ProcessingResult:
        """PDF를 로드하고 표를 LangChain Document로 추출한다 (HTML 우선 방식)."""
        validated_path = validate_pdf_path(pdf_path)
        document_name = validated_path.stem

        conv_dir = self.convert_pdf(pdf_path, output_dir, use_hybrid=use_hybrid)

        html_files = list(conv_dir.glob("*.html"))

        if not html_files:
            logger.warning("No HTML files found for %s", document_name)
            self._last_documents = []
            self._last_output_dir = conv_dir
            return ProcessingResult(
                documents_loaded=0,
                tables_extracted=0,
                document_name=document_name,
            )

        json_files = list(conv_dir.glob("*.json"))
        all_metadata: List[Dict[str, Any]] = []
        for json_file in json_files:
            metadata = parse_json_metadata(json_file)
            all_metadata.extend(metadata)

        logger.info("Found %d tables in JSON for %s", len(all_metadata), document_name)

        html_file = html_files[0]
        html_tables = extract_html_tables_from_file(html_file)
        logger.info("Extracted %d tables from HTML for %s", len(html_tables), document_name)

        if not html_tables:
            logger.warning("No tables found in HTML for %s", document_name)
            self._last_documents = []
            self._last_output_dir = conv_dir
            return ProcessingResult(
                documents_loaded=0,
                tables_extracted=0,
                document_name=document_name,
            )

        md_files = list(conv_dir.glob("*.md"))
        table_info_list: List[Dict[str, Any]] = []
        if md_files:
            md_file = md_files[0]
            markdown_tables = extract_markdown_tables_from_file(md_file)
            table_start_lines = [start_line for _, start_line in markdown_tables]
            table_info_list = extract_table_info(md_file, table_start_lines, all_metadata)
            logger.info("Extracted %d table info entries from markdown (titles + context)", len(table_info_list))

        documents: List[Document] = []
        used_json_indices: set = set()

        fitz_doc: Optional[Any] = None
        try:
            fitz_doc = fitz.open(str(validated_path))
        except Exception:
            logger.warning("Could not open PDF with PyMuPDF for cell-level extraction: %s", validated_path)

        for idx, (table_html_str, _offset, html_title, html_context) in enumerate(html_tables):
            table_title: Optional[str] = html_title
            table_context: Optional[str] = html_context
            page_estimate = 1

            if not table_title and idx < len(table_info_list):
                info = table_info_list[idx]
                table_title = info.get("title")
                if not table_context:
                    table_context = info.get("context")
                page_estimate = info.get("page_estimate", 1)

            page_number = page_estimate
            bounding_box: List[float] = [0, 0, 0, 0]
            table_id = f"table_{page_number}_{idx}"

            html_content = extract_table_text_content(table_html_str)
            best_match_idx = find_best_json_match(html_content, all_metadata, used_json_indices)

            if best_match_idx is not None:
                meta = all_metadata[best_match_idx]
                page_number = meta.get("page_number", page_estimate)
                bounding_box = meta.get("bounding_box", [0, 0, 0, 0])
                json_id = meta.get("id", best_match_idx)
                table_id = f"table_{page_number}_{json_id}"
                used_json_indices.add(best_match_idx)
                # docling/opendataloader-pdf bbox is already in PDF coords (bottom-left, y-up)
                # no conversion needed

            table_md = html_table_to_markdown(table_html_str)

            doc_metadata: Dict[str, Any] = {
                "page_number": page_number,
                "bounding_box": bounding_box,
                "table_id": table_id,
                "document_name": document_name,
                "table_html": table_html_str,
            }

            if table_title:
                doc_metadata["table_title"] = table_title
            if table_context:
                doc_metadata["table_context"] = table_context

            try:
                fitz_page = fitz_doc[page_number - 1] if fitz_doc and page_number <= len(fitz_doc) else None
                structure = extract_table_structure(
                    html=table_html_str,
                    table_id=table_id,
                    table_title=table_title or "",
                    page=fitz_page,
                )
                structured_text = structure.to_full_text()
                if len(structured_text.strip()) > 10:
                    content = structured_text
                    doc_metadata["doc_type"] = "full_table"
                    doc_metadata["table_html"] = table_html_str

                    doc = Document(page_content=content, metadata=doc_metadata)
                    documents.append(doc)

                    for ci, field in enumerate(structure.fields):
                        chunk_text = f"{field.path} : {field.value}"
                        if not chunk_text.strip():
                            continue
                        chunk_meta = dict(doc_metadata)
                        chunk_meta["doc_type"] = "cell_chunk"
                        chunk_meta["parent_table_id"] = table_id
                        chunk_meta["chunk_index"] = ci
                        chunk_meta["hierarchy_path"] = field.path
                        chunk_meta["key_field"] = field.key
                        chunk_meta["depth"] = field.depth
                        if field.supplementary:
                            chunk_meta["bounding_box"] = [0, 0, 0, 0]
                        documents.append(Document(page_content=chunk_text, metadata=chunk_meta))
                else:
                    content_parts = []
                    if table_title:
                        content_parts.append(table_title)
                    if table_context:
                        content_parts.append(table_context)
                    content_parts.append(table_html_str)
                    content = "\n".join(content_parts)
                    doc = Document(page_content=content, metadata=doc_metadata)
                    documents.append(doc)
            except Exception:
                content_parts = []
                if table_title:
                    content_parts.append(table_title)
                if table_context:
                    content_parts.append(table_context)
                content_parts.append(table_html_str)
                content = "\n".join(content_parts)
                doc = Document(page_content=content, metadata=doc_metadata)
                documents.append(doc)

        if fitz_doc:
            fitz_doc.close()

        logger.info("Parsed %d documents from HTML for %s", len(documents), document_name)

        self._last_documents = documents
        self._last_output_dir = conv_dir

        return ProcessingResult(
            documents_loaded=len(documents),
            tables_extracted=len(documents),
            document_name=document_name,
        )

    def convert_standard(self, pdf_path: str, output_dir: Optional[str] = None) -> Optional[Path]:
        """표준(비 hybrid) PDF 변환을 실행하고 HTML 파일 경로를 반환한다."""
        validated_path = Path(pdf_path)
        if output_dir:
            target = Path(output_dir) / "standard"
        else:
            target = self._get_output_dir(validated_path) / "standard"
        target.mkdir(parents=True, exist_ok=True)

        logger.info("Standard conversion: %s -> %s", validated_path, target)
        try:
            params = {
                "input_path": str(validated_path),
                "output_dir": str(target),
                "format": "html",
            }
            try:
                opendataloader_pdf.convert(**params)
            except TypeError:
                params.pop("format", None)
                opendataloader_pdf.convert(input_path=str(validated_path), output_dir=str(target))
        except Exception as exc:
            logger.warning("Standard conversion failed: %s", exc)
            return None

        html_files = list(target.glob("*.html"))
        if html_files:
            logger.info("Standard HTML produced: %s", html_files[0])
            return html_files[0]
        return None

    def get_documents(self) -> List[Document]:
        """가장 최근 로드한 LangChain Document를 반환한다."""
        return getattr(self, "_last_documents", [])
