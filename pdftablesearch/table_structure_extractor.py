"""Table Structure Extractor — HTML table → hierarchical path extraction.

Converts nested/key-value HTML tables into structured semantic chunks:
  path: "간이투자설명서 > 모집기간"
  value: "2022년 4월 25일 ~ 2022년 4월 27일"

Supports:
  - Key-value tables (interleaved <p> tags in single-cell outer table)
  - Grid tables (standard row×column)
  - Nested/inner tables (recursive hierarchy)
  - Multi-page merged tables
  - PyMuPDF cell-level extraction for nested tables (fallback for merged cells)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from bs4 import BeautifulSoup, Tag

if TYPE_CHECKING:
    import fitz

logger = logging.getLogger(__name__)


@dataclass
class StructuredField:
    path: str
    key: str
    value: str
    depth: int = 0
    source_page: Optional[int] = None
    supplementary: bool = False


@dataclass
class TableStructure:
    table_id: str
    table_title: str = ""
    fields: List[StructuredField] = field(default_factory=list)

    def to_full_text(self) -> str:
        lines = []
        if self.table_title:
            lines.append(f"[{self.table_title}]")
        for f in self.fields:
            lines.append(f"{f.path} : {f.value}")
        return "\n".join(lines)

    def to_cell_chunks(self) -> List[str]:
        return [f"{f.path} : {f.value}" for f in self.fields]

    def get_key_fields(self) -> List[str]:
        return list(dict.fromkeys(f.key for f in self.fields if f.key))

    def get_context_window(self, matched_key: str, window_size: int = 3) -> List[StructuredField]:
        matched_idx = None
        for i, f in enumerate(self.fields):
            if f.key == matched_key or matched_key in f.path:
                matched_idx = i
                break

        if matched_idx is None:
            return self.fields[:window_size * 2 + 1]

        matched_depth = self.fields[matched_idx].depth
        siblings = [
            (i, f) for i, f in enumerate(self.fields)
            if f.depth <= matched_depth
        ]

        sibling_idx = None
        for si, (orig_i, _) in enumerate(siblings):
            if orig_i == matched_idx:
                sibling_idx = si
                break

        if sibling_idx is None:
            return self.fields[max(0, matched_idx - window_size):matched_idx + window_size + 1]

        start = max(0, sibling_idx - window_size)
        end = min(len(siblings), sibling_idx + window_size + 1)
        result_indices = [siblings[j][0] for j in range(start, end)]

        fields_in_window = []
        for i in range(len(self.fields)):
            if i in result_indices:
                fields_in_window.append(self.fields[i])
            elif i > result_indices[0] and i < result_indices[-1]:
                fields_in_window.append(self.fields[i])

        return fields_in_window


def extract_table_structure(
    html: str,
    table_id: str = "",
    table_title: str = "",
    parent_path: Optional[List[str]] = None,
    page: Optional["fitz.Page"] = None,
) -> TableStructure:
    if parent_path is None:
        parent_path = [table_title] if table_title else []

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return TableStructure(table_id=table_id, table_title=table_title)

    outer = tables[0]
    html_fields = _parse_table(outer, parent_path, depth=0)

    if page is not None:
        pymupdf_fields = _extract_from_pymupdf(page, parent_path)
        if pymupdf_fields:
            html_keys = {f.key for f in html_fields if f.key}
            pymupdf_keys = {f.key for f in pymupdf_fields if f.key}
            missing_in_html = pymupdf_keys - html_keys
            if missing_in_html:
                for f in pymupdf_fields:
                    if f.key in missing_in_html:
                        f.supplementary = True
                        html_fields.append(f)
                logger.info("PyMuPDF supplemented %d fields: %s", len(missing_in_html), missing_in_html)

    return TableStructure(
        table_id=table_id,
        table_title=table_title,
        fields=html_fields,
    )


def _extract_from_pymupdf(
    page: "fitz.Page",
    parent_path: List[str],
) -> List[StructuredField]:
    try:
        import fitz
    except ImportError:
        return []

    tables = page.find_tables()
    if not tables.tables:
        return []

    fields: List[StructuredField] = []

    for tab in tables.tables:
        cells = tab.extract()
        if not cells:
            continue

        for ri, row in enumerate(cells):
            non_empty = [
                (ci, cell.strip().replace("\n", " "))
                for ci, cell in enumerate(row)
                if cell and cell.strip()
            ]

            i = 0
            while i < len(non_empty):
                ci_key, text_key = non_empty[i]

                if len(text_key) <= 25 and i + 1 < len(non_empty):
                    ci_val, text_val = non_empty[i + 1]
                    if ci_val > ci_key and len(text_val) > len(text_key):
                        path = " > ".join(parent_path + [text_key]) if parent_path else text_key
                        fields.append(StructuredField(
                            path=path, key=text_key,
                            value=text_val[:500], depth=0,
                            source_page=page.number + 1,
                        ))
                        i += 2
                        continue

                if len(text_key) > 25:
                    path = " > ".join(parent_path) if parent_path else ""
                    fields.append(StructuredField(
                        path=path, key="",
                        value=text_key[:500], depth=0,
                        source_page=page.number + 1,
                    ))
                i += 1

    return fields


def _parse_table(table: Tag, parent_path: List[str], depth: int) -> List[StructuredField]:
    rows = table.find_all("tr", recursive=False)
    if not rows:
        return []

    if len(rows) == 1:
        cells = rows[0].find_all(["td", "th"], recursive=False)
        if len(cells) == 1:
            return _parse_single_cell_table(cells[0], parent_path, depth)

    has_header_row = any(
        all(c.name == "th" for c in row.find_all(["td", "th"], recursive=False))
        for row in rows
    )

    if has_header_row:
        return _parse_grid_table(rows, parent_path, depth)
    else:
        return _parse_key_value_rows(rows, parent_path, depth)


def _parse_single_cell_table(cell: Tag, parent_path: List[str], depth: int) -> List[StructuredField]:
    fields: List[StructuredField] = []

    children = []
    for child in cell.children:
        if not hasattr(child, "name") or child.name is None:
            continue
        if child.name in ("p", "h4", "h5", "h6"):
            text = child.get_text(strip=True)
            if text:
                children.append(("text", text))
        elif child.name == "figcaption":
            text = child.get_text(strip=True)
            if text and len(text) > 5:
                children.append(("caption", text))
        elif child.name == "table":
            children.append(("table", child))
        elif child.name == "ul":
            items = [li.get_text(strip=True) for li in child.find_all("li") if li.get_text(strip=True)]
            if items:
                children.append(("list", items))

    i = 0
    while i < len(children):
        typ, content = children[i]

        if typ == "table":
            sub_fields = _parse_table(content, parent_path, depth + 1)
            fields.extend(sub_fields)
            i += 1
            continue

        if typ == "list":
            for item in content:
                path = " > ".join(parent_path + [item]) if parent_path else item
                fields.append(StructuredField(path=path, key=item, value="", depth=depth))
            i += 1
            continue

        if typ == "caption":
            i += 1
            continue

        if typ == "text":
            is_short_label = len(content) <= 20 and not _looks_like_value(content)

            if is_short_label and i + 1 < len(children):
                next_typ, next_content = children[i + 1]
                if next_typ == "text" and len(next_content) > len(content):
                    path = " > ".join(parent_path + [content]) if parent_path else content
                    fields.append(StructuredField(
                        path=path, key=content,
                        value=next_content[:500], depth=depth,
                    ))
                    i += 2
                    continue

            inline = _try_split_inline_kv(content, parent_path, depth)
            if inline:
                fields.extend(inline)
                i += 1
                continue

            i += 1
            continue

        i += 1

    return fields


_KNOWN_INLINE_KEYS = {
    "집합투자업자", "모집∙매출 총액", "모집·매출 총액", "존속기간",
    "판매회사", "과세", "투자위험등급", "분류", "투자비용",
    "산정방법", "공시장소", "기준가",
}


def _try_split_inline_kv(text: str, parent_path: List[str], depth: int) -> Optional[List[StructuredField]]:
    results: List[StructuredField] = []

    for known_key in _KNOWN_INLINE_KEYS:
        if text.startswith(known_key):
            remainder = text[len(known_key):].strip()
            if remainder:
                path = " > ".join(parent_path + [known_key]) if parent_path else known_key
                results.append(StructuredField(path=path, key=known_key, value=remainder[:500], depth=depth))
                return results

    combined_pairs = [
        ("효력발생일", "존속기간"),
    ]
    for k1, k2 in combined_pairs:
        if k1 in text and k2 in text:
            parts = text.split(k2, 1)
            v1 = parts[0].replace(k1, "").strip()
            if v1:
                path1 = " > ".join(parent_path + [k1]) if parent_path else k1
                results.append(StructuredField(path=path1, key=k1, value=v1, depth=depth))
            v2 = parts[1].strip() if len(parts) > 1 else ""
            if v2:
                path2 = " > ".join(parent_path + [k2]) if parent_path else k2
                results.append(StructuredField(path=path2, key=k2, value=v2, depth=depth))
            return results if results else None

    return None


def _parse_grid_table(rows: List[Tag], parent_path: List[str], depth: int) -> List[StructuredField]:
    fields: List[StructuredField] = []

    header_row = rows[0]
    header_cells = header_row.find_all(["td", "th"], recursive=False)
    col_headers = [c.get_text(strip=True) for c in header_cells]

    for row in rows[1:]:
        cells = row.find_all(["td", "th"], recursive=False)
        if not cells:
            continue

        row_key = cells[0].get_text(strip=True)

        inner_tables = cells[0].find_all("table", recursive=False)
        if inner_tables:
            sub_path = parent_path + [row_key] if parent_path else [row_key]
            for inner in inner_tables:
                sub_fields = _parse_table(inner, sub_path, depth + 1)
                fields.extend(sub_fields)
            if len(cells) > 1:
                val = cells[1].get_text(strip=True)
                if val:
                    path = " > ".join(sub_path)
                    fields.append(StructuredField(path=path, key=row_key, value=val[:500], depth=depth))
            continue

        if len(cells) >= 2:
            for ci in range(1, len(cells)):
                val = cells[ci].get_text(strip=True)
                if not val:
                    continue

                col_header = col_headers[ci] if ci < len(col_headers) else ""

                if col_header and col_header != row_key:
                    path_parts = parent_path + [row_key, col_header] if parent_path else [row_key, col_header]
                    key = f"{row_key} > {col_header}"
                else:
                    path_parts = parent_path + [row_key] if parent_path else [row_key]
                    key = row_key

                path = " > ".join(path_parts)
                fields.append(StructuredField(path=path, key=key, value=val[:500], depth=depth))
        elif len(cells) == 1 and row_key:
            path = " > ".join(parent_path + [row_key]) if parent_path else row_key
            fields.append(StructuredField(path=path, key=row_key, value="", depth=depth))

    return fields


def _parse_key_value_rows(rows: List[Tag], parent_path: List[str], depth: int) -> List[StructuredField]:
    fields: List[StructuredField] = []

    for row in rows:
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True)
            val = cells[1].get_text(strip=True)

            inner = cells[1].find("table", recursive=False)
            if inner:
                sub_path = parent_path + [key] if parent_path else [key]
                sub_fields = _parse_table(inner, sub_path, depth + 1)
                fields.extend(sub_fields)
            elif key and val:
                path = " > ".join(parent_path + [key]) if parent_path else key
                fields.append(StructuredField(path=path, key=key, value=val[:500], depth=depth))

    return fields


def _looks_like_value(text: str) -> bool:
    value_indicators = ["~", "년", "월", "일", "원", "억", "%", "http", "www", "없음", "해당"]
    return any(ind in text for ind in value_indicators)
