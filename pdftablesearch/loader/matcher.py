"""Content-based matching between HTML tables and JSON metadata.

Uses Jaccard word-overlap similarity to associate HTML-extracted tables
with their corresponding JSON metadata entries (page numbers, bounding
boxes).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

_MINIMUM_MATCH_THRESHOLD = 0.3


def calculate_table_similarity(html_content: str, json_meta: Dict[str, Any]) -> float:
    """Compute similarity between HTML table text and JSON table metadata.

    Uses Jaccard similarity on normalized word sets.
    """
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
    """Find the best matching JSON table index for an HTML table.

    Args:
        html_content: Normalized text from the HTML table.
        all_metadata: All parsed JSON metadata entries.
        used_indices: Indices already claimed by prior matches.

    Returns:
        Best matching index, or ``None`` if below threshold.
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
