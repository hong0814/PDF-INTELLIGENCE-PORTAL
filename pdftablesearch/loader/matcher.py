"""HTML 표와 JSON 메타데이터 간 콘텐츠 기반 매칭.

Jaccard 단어 오버랩 유사도를 사용하여 HTML에서 추출한 표와
해당 JSON 메타데이터 항목(페이지 번호, 바운딩 박스)을 연결한다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

_MINIMUM_MATCH_THRESHOLD = 0.3


def calculate_table_similarity(html_content: str, json_meta: Dict[str, Any]) -> float:
    """HTML 표 텍스트와 JSON 표 메타데이터 간 Jaccard 유사도를 계산한다."""
    table_data = json_meta.get("table_data", {})
    json_rows = table_data.get("rows", [])

    if not json_rows:
        return 0.0

    json_text_parts: List[str] = []
    for row in json_rows:
        if isinstance(row, dict):
            cells = row.get("cells", [])
            cell_texts: List[str] = []
            for cell in cells:
                if isinstance(cell, dict):
                    kids = cell.get("kids", [])
                    if isinstance(kids, list):
                        text = " ".join(
                            k.get("content", "")
                            for k in kids
                            if isinstance(k, dict) and "content" in k
                        ).strip()
                        cell_texts.append(text)
            if cell_texts:
                json_text_parts.append(" | ".join(cell_texts))

    json_content = " || ".join(json_text_parts)

    if not html_content or not json_content:
        return 0.0

    html_normalized = html_content.lower().replace(" ", "")
    json_normalized = json_content.lower().replace(" ", "")

    if json_normalized in html_normalized or html_normalized in json_normalized:
        return 0.9

    html_words: Set[str] = set(html_normalized.split())
    json_words: Set[str] = set(json_normalized.split())

    if not html_words or not json_words:
        return 0.0

    intersection = html_words & json_words
    union = html_words | json_words

    return len(intersection) / len(union) if union else 0.0


def find_best_json_match(
    html_content: str,
    all_metadata: List[Dict[str, Any]],
    used_indices: Set[int],
) -> Optional[int]:
    """HTML 표에 가장 잘 매칭되는 JSON 표 인덱스를 찾는다.

    임계값 미만이면 ``None``을 반환한다.
    """
    best_idx: Optional[int] = None
    best_score = _MINIMUM_MATCH_THRESHOLD

    for idx, meta in enumerate(all_metadata):
        if idx in used_indices:
            continue
        score = calculate_table_similarity(html_content, meta)
        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx
