"""Markdown 표 추출 및 컨텍스트/제목 파싱."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR_RE = re.compile(r"^\s*\|[-:]+\|.*\|[-:]+\|?\s*$")


def extract_markdown_tables(markdown_content: str) -> List[str]:
    """콘텐츠 문자열에서 마크다운 표를 추출한다."""
    tables: List[str] = []
    current_table_lines: List[str] = []

    for line in markdown_content.split("\n"):
        stripped = line.strip()
        if _TABLE_ROW_RE.match(stripped):
            current_table_lines.append(stripped)
        else:
            if current_table_lines and len(current_table_lines) >= 2:
                if _SEPARATOR_RE.match(current_table_lines[1]):
                    tables.append("\n".join(current_table_lines))
            current_table_lines = []

    if current_table_lines and len(current_table_lines) >= 2:
        if _SEPARATOR_RE.match(current_table_lines[1]):
            tables.append("\n".join(current_table_lines))

    return tables


def extract_markdown_tables_from_file(
    markdown_path: "Path",
) -> List[Tuple[str, int]]:
    """마크다운 표와 시작 줄 번호를 함께 추출한다."""
    from pathlib import Path

    if not markdown_path.exists():
        return []

    try:
        with open(markdown_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (UnicodeDecodeError, IOError):
        return []

    tables: List[Tuple[str, int]] = []
    current_table_lines: List[str] = []
    start_line = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if _TABLE_ROW_RE.match(stripped):
            if not current_table_lines:
                start_line = i
            current_table_lines.append(stripped)
        else:
            if current_table_lines and len(current_table_lines) >= 2:
                if _SEPARATOR_RE.match(current_table_lines[1]):
                    tables.append(("\n".join(current_table_lines), start_line))
            current_table_lines = []

    if current_table_lines and len(current_table_lines) >= 2:
        if _SEPARATOR_RE.match(current_table_lines[1]):
            tables.append(("\n".join(current_table_lines), start_line))

    return tables


def extract_table_info(
    markdown_path: "Path",
    table_start_lines: List[int],
    json_metadata: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """주어진 표 위치에서 제목과 컨텍스트를 추출한다.

    ``title``, ``context`` 키를 가진 딕셔너리 리스트를 반환한다.
    """
    from pathlib import Path

    if not markdown_path.exists():
        return []

    try:
        with open(markdown_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (UnicodeDecodeError, IOError):
        return []

    if not table_start_lines:
        return []

    table_info_list: List[Dict[str, Any]] = []
    for table_line in table_start_lines:
        title: Optional[str] = None
        context_parts: List[str] = []

        start_line = max(0, table_line - 15)
        for offset in range(1, min(16, table_line - start_line + 1)):
            check_line = table_line - offset
            line = lines[check_line].strip()

            if not line or _TABLE_ROW_RE.match(line) or _SEPARATOR_RE.match(line):
                continue

            if not title:
                angle_match = re.match(r"^#{1,6}\s*<([^>]+)>", line)
                if angle_match:
                    title = angle_match.group(1).strip()

            if not title:
                header_match = re.match(r"^#{1,6}\s+(.+)$", line)
                if header_match:
                    potential_title = header_match.group(1).strip()
                    if len(potential_title) > 2 and not potential_title.replace(".", "").replace("-", "").replace(" ", "").isdigit():
                        title = potential_title

            if not title:
                list_match = re.match(r"^[-\*]+\s*(.+)$", line)
                if list_match:
                    potential_title = list_match.group(1).strip()
                    if len(potential_title) > 2:
                        title = potential_title

            if len(context_parts) < 5:
                context_parts.insert(0, line)

        context_text = " ".join(context_parts) if context_parts else None

        table_info_list.append(
            {
                "title": title,
                "context": context_text[:300] if context_text else None,
            }
        )

    if json_metadata:
        pages_with_tables = sorted(
            set(meta.get("page_number", 1) for meta in json_metadata)
        )
        num_pages = len(pages_with_tables)
        total_tables = len(table_info_list)

        for i, table_info in enumerate(table_info_list):
            if num_pages > 1:
                page_idx = min(i * num_pages // total_tables, num_pages - 1)
                table_info["page_estimate"] = pages_with_tables[page_idx]
            else:
                table_info["page_estimate"] = 1

    return table_info_list
