"""PDF document loading via opendataloader-pdf (HTML-first approach).

This package provides the :class:`PDFProcessor` class and supporting
functions for PDF-to-document conversion.  The implementation is split
across focused submodules but all public symbols are re-exported here
for backward compatibility.

Submodules:
    html_parser: HTML table extraction, sanitization, HTML-to-Markdown.
    json_parser: JSON metadata parsing from opendataloader-pdf output.
    markdown_parser: Markdown table extraction and title/context parsing.
    matcher: Content-based HTML↔JSON table matching (Jaccard similarity).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    calculate_table_similarity,
    find_best_json_match,
)

logger = get_logger(__name__)

# Re-export regex constants for backward compatibility
import re
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR_RE = re.compile(r"^\s*\|[-:]+\|.*\|[-:]+\|?\s*$")


class PDFProcessor:
    """Handles PDF document loading via opendataloader-pdf (HTML-first approach)."""

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
        """Convert PDF to Markdown + JSON using opendataloader-pdf."""
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
        """Load PDF and extract tables as LangChain Documents (HTML-first approach).

        Extracts tables from HTML as primary source, using JSON metadata for
        page numbers and bounding boxes. Each Document carries both the raw
        HTML (``metadata["table_html"]``) and a Markdown fallback
        (``page_content``).
        """
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

        for idx, (table_html_str, _offset, html_title) in enumerate(html_tables):
            table_title: Optional[str] = html_title
            table_context: Optional[str] = None
            page_estimate = 1

            if not table_title and idx < len(table_info_list):
                info = table_info_list[idx]
                table_title = info.get("title")
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
            else:
                if all_metadata:
                    num_json_tables = len(all_metadata)
                    closest_idx = min(
                        (i for i in range(num_json_tables) if i not in used_json_indices),
                        key=lambda x: abs(x - idx),
                        default=None,
                    )
                    if closest_idx is not None:
                        page_estimate = all_metadata[closest_idx].get("page_number", page_estimate)
                page_number = page_estimate

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

            content = f"{table_title}\n{table_html_str}" if table_title else table_html_str

            doc = Document(page_content=content, metadata=doc_metadata)
            documents.append(doc)

        logger.info("Parsed %d tables from HTML for %s", len(documents), document_name)

        self._last_documents = documents
        self._last_output_dir = conv_dir

        return ProcessingResult(
            documents_loaded=len(documents),
            tables_extracted=len(documents),
            document_name=document_name,
        )

    def get_documents(self) -> List[Document]:
        """Return the LangChain Documents from the most recent load."""
        return getattr(self, "_last_documents", [])
