"""HTML 표 추출, 정제, 변환.

opendataloader-pdf가 생성한 HTML 파일에서 표를 추출하고,
안전한 렌더링을 위해 정제하며, Markdown 폴백 형식으로 변환한다.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


def extract_html_tables_from_file(
    html_path: "Path",
) -> List[Tuple[str, int, Optional[str], Optional[str]]]:
    """HTML 파일에서 모든 ``<table>`` 요소를 추출한다.

    (table_html, index, title, context) 튜플 리스트를 반환한다.
    """
    from pathlib import Path

    if not html_path.exists():
        return []

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (UnicodeDecodeError, IOError):
        return []

    soup = BeautifulSoup(content, "html.parser")
    tables = soup.find_all("table")

    result: List[Tuple[str, int, Optional[str], Optional[str]]] = []
    for idx, table_tag in enumerate(tables):
        title: Optional[str] = None
        prev_sibling = table_tag.find_previous_sibling(
            ["h1", "h2", "h3", "h4", "h5", "h6"]
        )
        if prev_sibling:
            title = prev_sibling.get_text(separator=" ", strip=True)
            title = re.sub(r"^[\d\w가나다라마바사아자차카타파하]+\.\s+", "", title)
            title = title.strip()

        context_parts: List[str] = []
        for sib in table_tag.previous_siblings:
            if hasattr(sib, "get_text"):
                text = sib.get_text(separator=" ", strip=True)
            elif isinstance(sib, str) and sib.strip():
                text = sib.strip()
            else:
                continue
            if text:
                context_parts.append(text)
            if len(context_parts) >= 5:
                break
        context_parts.reverse()
        after_parts: List[str] = []
        for sib in table_tag.next_siblings:
            if hasattr(sib, "get_text"):
                text = sib.get_text(separator=" ", strip=True)
            elif isinstance(sib, str) and sib.strip():
                text = sib.strip()
            else:
                continue
            if text:
                after_parts.append(text)
            if len(after_parts) >= 2:
                break

        before_text = " ".join(context_parts)[:500]
        after_text = " ".join(after_parts)[:200]
        context = ""
        if before_text:
            context += before_text
        if after_text:
            context += (" " if context else "") + after_text
        context = context.strip() or None

        table_html = sanitize_table_html(str(table_tag))
        result.append((table_html, idx, title, context))

    return result


def extract_table_text_content(html_table: str) -> str:
    """유사도 매칭을 위해 HTML 표에서 정규화된 텍스트를 추출한다."""
    soup = BeautifulSoup(html_table, "html.parser")
    table = soup.find("table")
    if not table:
        return ""

    rows_text: List[str] = []
    for tr in table.find_all("tr"):
        cells_text: List[str] = []
        for cell in tr.find_all(["td", "th"]):
            cells_text.append(cell.get_text(separator=" ", strip=True))
        if cells_text:
            rows_text.append(" | ".join(cells_text))

    return " || ".join(rows_text)


def sanitize_table_html(table_html: str) -> str:
    """HTML 표에서 script 태그, 이벤트 핸들러, javascript: URL을 제거한다."""
    soup = BeautifulSoup(table_html, "html.parser")

    for script in soup.find_all("script"):
        script.decompose()

    event_attrs = [
        "onclick", "ondblclick", "onmousedown", "onmouseup", "onmouseover",
        "onmousemove", "onmouseout", "onkeydown", "onkeypress", "onkeyup",
        "onload", "onerror", "onfocus", "onblur", "onsubmit", "onreset",
        "onchange", "oninput",
    ]
    for tag in soup.find_all(True):
        for attr in event_attrs:
            if tag.has_attr(attr):
                del tag[attr]
        for url_attr in ("href", "src"):
            if tag.has_attr(url_attr):
                val = tag[url_attr].strip().lower()
                if val.startswith("javascript:") or val.startswith("data:text/html"):
                    del tag[url_attr]

    return str(soup)


def html_table_to_markdown(table_html: str) -> str:
    """HTML 표를 간단한 Markdown 표현으로 변환한다.

    병합 셀(colspan/rowspan)은 내용 반복으로 확장한다.
    """
    soup = BeautifulSoup(table_html, "html.parser")
    table = soup.find("table")
    if not table:
        return ""

    rows_data: List[List[str]] = []
    rowspan_grid: Dict[Tuple[int, int], str] = {}

    for row_idx, tr in enumerate(table.find_all("tr")):
        cells = tr.find_all(["td", "th"])
        col_idx = 0
        row_cells: List[str] = []

        for cell in cells:
            while (row_idx, col_idx) in rowspan_grid:
                row_cells.append(rowspan_grid[(row_idx, col_idx)])
                col_idx += 1

            text = cell.get_text(separator=" ", strip=True)
            colspan = int(cell.get("colspan", 1))
            rowspan = int(cell.get("rowspan", 1))

            for c in range(colspan):
                row_cells.append(text)
                for r in range(1, rowspan):
                    rowspan_grid[(row_idx + r, col_idx + c)] = text
                col_idx += 1

        while (row_idx, col_idx) in rowspan_grid:
            row_cells.append(rowspan_grid[(row_idx, col_idx)])
            col_idx += 1

        if row_cells:
            rows_data.append(row_cells)

    if not rows_data:
        return "| Empty table |\n|---|"

    max_cols = max(len(r) for r in rows_data)
    for row in rows_data:
        while len(row) < max_cols:
            row.append("")

    md_lines: List[str] = []
    for i, row in enumerate(rows_data):
        md_lines.append("|" + "|".join(row[:max_cols]) + "|")
        if i == 0:
            md_lines.append("|" + "|".join(["---"] * max_cols) + "|")

    return "\n".join(md_lines)
