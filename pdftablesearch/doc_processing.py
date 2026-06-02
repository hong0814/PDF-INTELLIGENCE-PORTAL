"""문서 처리 유틸리티 — HTML 블록 추출, 텍스트 분할, 청킹."""

from __future__ import annotations

import re


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
