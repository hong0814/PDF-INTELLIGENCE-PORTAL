"""opendataloader-pdf JSON 출력에서 테이블 메타데이터 파싱."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from pdftablesearch.utils import get_logger

logger = get_logger(__name__)


def _extract_table_entries(data: Any) -> List[Dict[str, Any]]:
    """Return table entries from supported opendataloader-pdf JSON shapes."""
    entries: List[Dict[str, Any]] = []

    def add_from_kids(kids: Any) -> None:
        if not isinstance(kids, list):
            return
        for entry in kids:
            if isinstance(entry, dict) and entry.get("type") == "table":
                entries.append(entry)

    if isinstance(data, dict):
        add_from_kids(data.get("kids"))
        pages = data.get("pages")
        if isinstance(pages, list):
            for page in pages:
                if isinstance(page, dict):
                    add_from_kids(page.get("kids"))
    elif isinstance(data, list):
        for page in data:
            if isinstance(page, dict):
                add_from_kids(page.get("kids"))

    return entries


def parse_json_metadata(json_path: "Path") -> List[Dict[str, Any]]:
    """opendataloader-pdf JSON 출력에서 표 메타데이터를 파싱한다.

    ``page_number``, ``bounding_box``, ``index``, ``id``, ``table_data`` 키를 가진
    딕셔너리 리스트를 반환한다.
    """
    from pathlib import Path

    if not json_path.exists():
        logger.warning("JSON metadata file not found: %s", json_path)
        return []

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error("Failed to parse JSON metadata: %s", exc)
        return []

    result: List[Dict[str, Any]] = []
    table_idx = 0

    for entry in _extract_table_entries(data):
        if table_idx == 0:
            logger.info("First table entry keys: %s", list(entry.keys()))

        bbox = entry.get("bounding box", [])
        if isinstance(bbox, list) and len(bbox) >= 4:
            bounding_box = [
                float(v) if isinstance(v, (int, float)) else 0.0 for v in bbox[:4]
            ]
        else:
            bounding_box = [0.0, 0.0, 0.0, 0.0]

        page_num = entry.get("page number", entry.get("page_number", 1))

        result.append(
            {
                "page_number": page_num,
                "bounding_box": bounding_box,
                "index": table_idx,
                "table_index": table_idx,
                "id": entry.get("id", table_idx),
                "table_data": entry,
            }
        )
        table_idx += 1

    logger.info("Extracted %d tables from JSON", len(result))
    return result


def reconstruct_table_markdown(table_meta: Dict[str, Any]) -> str:
    """JSON 셀 데이터에서 마크다운 표를 재구성한다."""
    table_data = table_meta.get("table_data", table_meta)
    rows = table_data.get("rows", [])
    num_cols = table_data.get("num_cols", table_data.get("number of columns", 0))

    if not rows:
        return ""

    md_lines: List[str] = []
    for row_idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        cells = row.get("cells", [])
        cell_texts: List[str] = []
        for cell in cells:
            if not isinstance(cell, dict):
                cell_texts.append("")
                continue
            kids = cell.get("kids", [])
            if isinstance(kids, list):
                text = " ".join(
                    child.get("content", "")
                    for child in kids
                    if isinstance(child, dict) and "content" in child
                ).strip()
            else:
                text = ""
            cell_texts.append(text if text else "")

        md_lines.append("|" + "|".join(cell_texts) + "|")
        if row_idx == 0 and num_cols > 0:
            md_lines.append("|" + "|".join(["---"] * num_cols) + "|")

    return "\n".join(md_lines)
