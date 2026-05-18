"""HTML table extraction, sanitization, and conversion.

Provides helpers to extract tables from HTML files produced by
opendataloader-pdf, sanitize them for safe rendering, and convert
them to Markdown fallback format.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


def extract_html_tables_from_file(
    html_path: "Path",
) -> List[Tuple[str, int, Optional[str]]]:
    """Extract all ``<table>`` elements from an HTML file.

    Returns list of (table_html, index, title) tuples.  The title is the
    text of the nearest h1-h6 tag preceding the table.
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

    result: List[Tuple[str, int, Optional[str]]] = []
    for idx, table_tag in enumerate(tables):
        title: Optional[str] = None
        prev_sibling = table_tag.find_previous_sibling(
            ["h1", "h2", "h3", "h4", "h5", "h6"]
        )
        if prev_sibling:
            title = prev_sibling.get_text(separator=" ", strip=True)
            title = re.sub(r"^[\d\w가나다라마바사아자차카타파하]+\.\s+", "", title)
            title = title.strip()

        table_html = sanitize_table_html(str(table_tag))
        result.append((table_html, idx, title))

    return result


def extract_table_text_content(html_table: str) -> str:
    """Extract normalized text content from an HTML table for similarity matching."""
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
    """Remove script tags, event handlers, and javascript: URLs from an HTML table."""
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
    """Convert an HTML table to a simplified Markdown representation.

    Merged cells (colspan/rowspan) are expanded by repeating content.
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
