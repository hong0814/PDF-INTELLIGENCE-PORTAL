"""Tests for pdftablesearch.loader module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdftablesearch.loader import (
    PDFProcessor,
    _extract_markdown_tables,
    _extract_table_entries,
    _parse_json_metadata,
    _read_markdown_file,
    _reconstruct_table_markdown,
)
from pdftablesearch.exceptions import PDFProcessingError, TableParsingError


# ---------------------------------------------------------------------------
# Helper: build opendataloader-pdf style JSON
# ---------------------------------------------------------------------------

def _make_opendataloader_json(tables: list[dict]) -> dict:
    """Build a JSON structure mimicking opendataloader-pdf output.

    Args:
        tables: List of dicts with keys like ``id``, ``page number``,
            ``bounding box``, ``number of rows``, ``number of columns``,
            ``rows``.

    Returns:
        A dict with a ``kids`` array containing the table entries
        interleaved with non-table elements to test filtering.
    """
    kids = []
    # Add some non-table elements to verify filtering works
    kids.append({"type": "heading", "id": 1, "content": "Title", "page number": 1})
    for t in tables:
        entry = {"type": "table", **t}
        kids.append(entry)
        kids.append({"type": "paragraph", "id": t.get("id", 0) + 1000, "content": "text"})
    kids.append({"type": "heading", "id": 999, "content": "End"})
    return {"file name": "test.pdf", "number of pages": 1, "kids": kids}


def _make_table_entry(
    table_id: int = 100,
    page: int = 1,
    bbox: list | None = None,
    rows: list | None = None,
    num_rows: int = 2,
    num_cols: int = 2,
) -> dict:
    """Create a single table entry for JSON construction.

    Args:
        table_id: Table ID.
        page: 1-indexed page number.
        bbox: Bounding box ``[x1, y1, x2, y2]``.
        rows: Row data. If ``None``, a simple 2x2 table is generated.
        num_rows: Number of rows (used if rows is None).
        num_cols: Number of columns (used if rows is None).

    Returns:
        Dict representing a table entry.
    """
    if bbox is None:
        bbox = [0, 0, 500, 200]
    if rows is None:
        # Generate simple rows with cell content
        rows_data = []
        for r in range(1, num_rows + 1):
            cells = []
            for c in range(1, num_cols + 1):
                text = f"R{r}C{c}" if r > 1 else f"H{c}"
                cells.append({
                    "type": "table cell",
                    "page number": page,
                    "row number": r,
                    "column number": c,
                    "row span": 1,
                    "column span": 1,
                    "kids": [{"type": "paragraph", "content": text}],
                })
            rows_data.append({
                "type": "table row",
                "row number": r,
                "cells": cells,
            })
        rows = rows_data

    return {
        "id": table_id,
        "page number": page,
        "bounding box": bbox,
        "number of rows": num_rows,
        "number of columns": num_cols,
        "rows": rows,
    }


# ===========================================================================
# TestExtractMarkdownTables
# ===========================================================================


class TestExtractMarkdownTables:
    """Tests for _extract_markdown_tables function."""

    def test_single_table(self):
        md = """Some text before.

| Header1 | Header2 |
|---------|---------|
| A       | B       |
| C       | D       |

Some text after."""

        tables = _extract_markdown_tables(md)
        assert len(tables) == 1
        assert "Header1" in tables[0]
        assert "A" in tables[0]

    def test_multiple_tables(self):
        md = """| T1H1 | T1H2 |
|------|------|
| 1    | 2    |

Some text between tables.

| T2H1 | T2H2 |
|------|------|
| 3    | 4    |"""

        tables = _extract_markdown_tables(md)
        assert len(tables) == 2
        assert "T1H1" in tables[0]
        assert "T2H1" in tables[1]

    def test_no_tables(self):
        md = "This is just text with no tables."
        tables = _extract_markdown_tables(md)
        assert len(tables) == 0

    def test_incomplete_table_skipped(self):
        """A single pipe row without a separator should not count as a table."""
        md = "| Only header | No separator |"
        tables = _extract_markdown_tables(md)
        assert len(tables) == 0

    def test_table_at_end_of_file(self):
        md = """Some text

| H1 | H2 |
|----|----|
| X  | Y  |"""

        tables = _extract_markdown_tables(md)
        assert len(tables) == 1

    def test_empty_input(self):
        assert _extract_markdown_tables("") == []


# ===========================================================================
# TestReadMarkdownFile
# ===========================================================================


class TestReadMarkdownFile:
    def test_valid_file(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Title\n\nContent", encoding="utf-8")
        content = _read_markdown_file(md_file)
        assert "Title" in content

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(TableParsingError, match="Failed to read"):
            _read_markdown_file(tmp_path / "nonexistent.md")


# ===========================================================================
# TestParseJsonMetadata
# ===========================================================================


class TestParseJsonMetadata:
    """Tests for JSON metadata parsing with opendataloader-pdf format."""

    def test_opendataloader_format_with_kids(self, tmp_path):
        """Standard opendataloader-pdf format with top-level kids array."""
        data = _make_opendataloader_json([
            _make_table_entry(table_id=100, page=1, bbox=[10, 20, 300, 400]),
            _make_table_entry(table_id=200, page=2, bbox=[50, 60, 500, 600]),
        ])
        json_file = tmp_path / "meta.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = _parse_json_metadata(json_file)
        assert len(result) == 2
        assert result[0]["id"] == 100
        assert result[0]["page_number"] == 1
        assert result[0]["bounding_box"] == [10, 20, 300, 400]
        assert result[0]["table_index"] == 0
        assert result[1]["id"] == 200
        assert result[1]["page_number"] == 2
        assert result[1]["table_index"] == 1

    def test_missing_file(self, tmp_path):
        result = _parse_json_metadata(tmp_path / "missing.json")
        assert result == []

    def test_invalid_json(self, tmp_path):
        json_file = tmp_path / "bad.json"
        json_file.write_text("not valid json{{{")

        result = _parse_json_metadata(json_file)
        assert result == []

    def test_no_table_entries(self, tmp_path):
        """Kids array with no table-type entries returns empty list."""
        data = {
            "kids": [
                {"type": "heading", "content": "Title"},
                {"type": "paragraph", "content": "Text"},
            ]
        }
        json_file = tmp_path / "empty.json"
        json_file.write_text(json.dumps(data))

        result = _parse_json_metadata(json_file)
        assert result == []

    def test_page_array_format(self, tmp_path):
        """Fallback: pages array with kids in each page."""
        data = {
            "pages": [
                {
                    "kids": [
                        {"type": "table", "id": 10, "page number": 1,
                         "bounding box": [1, 2, 3, 4],
                         "number of rows": 2, "number of columns": 2, "rows": []},
                    ]
                },
            ]
        }
        json_file = tmp_path / "meta.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = _parse_json_metadata(json_file)
        assert len(result) == 1
        assert result[0]["id"] == 10

    def test_list_format(self, tmp_path):
        """Fallback: list of page objects."""
        data = [
            {
                "kids": [
                    {"type": "table", "id": 5, "page number": 1,
                     "bounding box": [0, 0, 100, 100],
                     "number of rows": 1, "number of columns": 1, "rows": []},
                ]
            }
        ]
        json_file = tmp_path / "meta.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = _parse_json_metadata(json_file)
        assert len(result) == 1
        assert result[0]["id"] == 5

    def test_table_index_sequential(self, tmp_path):
        """Table indices are 0-based sequential regardless of kids position."""
        data = _make_opendataloader_json([
            _make_table_entry(table_id=872),
            _make_table_entry(table_id=927),
            _make_table_entry(table_id=991),
        ])
        json_file = tmp_path / "meta.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = _parse_json_metadata(json_file)
        assert len(result) == 3
        assert result[0]["table_index"] == 0
        assert result[1]["table_index"] == 1
        assert result[2]["table_index"] == 2


# ===========================================================================
# TestReconstructTableMarkdown
# ===========================================================================


class TestReconstructTableMarkdown:
    """Tests for JSON-to-markdown table reconstruction."""

    def test_simple_table(self):
        meta = _make_table_entry(num_rows=3, num_cols=2)
        md = _reconstruct_table_markdown(meta)
        lines = md.split("\n")
        # Header row + separator + 2 data rows
        assert len(lines) == 4
        assert lines[0] == "|H1|H2|"
        assert lines[1] == "|---|---|"
        assert lines[2] == "|R2C1|R2C2|"
        assert lines[3] == "|R3C1|R3C2|"

    def test_empty_rows(self):
        meta = {"rows": [], "num_cols": 3}
        md = _reconstruct_table_markdown(meta)
        assert md == ""

    def test_single_row(self):
        meta = _make_table_entry(num_rows=1, num_cols=3)
        md = _reconstruct_table_markdown(meta)
        lines = md.split("\n")
        assert len(lines) == 2  # header + separator
        assert "|H1|H2|H3|" in lines[0]
        assert "|---|---|---|" in lines[1]


# ===========================================================================
# TestPDFProcessor
# ===========================================================================


class TestPDFProcessor:
    """Tests for PDFProcessor class."""

    def test_init_defaults(self):
        processor = PDFProcessor()
        assert processor.parallel_workers == 4

    def test_init_custom_workers(self):
        processor = PDFProcessor(parallel_workers=8)
        assert processor.parallel_workers == 8

    def test_get_documents_empty_initially(self):
        processor = PDFProcessor()
        assert processor.get_documents() == []

    def test_parse_tables_json_only(self, tmp_path):
        """Tables extracted from JSON even without markdown content.

        When JSON has tables but markdown has no tables (or no MD file),
        tables are reconstructed from JSON cell data.
        """
        processor = PDFProcessor()

        # Only JSON, no MD
        data = _make_opendataloader_json([
            _make_table_entry(table_id=100, page=1, num_rows=2, num_cols=2),
        ])
        json_file = tmp_path / "output.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        # No MD file -- parse_tables needs at least one .md file to not
        # raise the old error, but in the new code, JSON-first means
        # we check JSON first. Actually, the old code raises if no .md.
        # New code: we need to handle this.
        # Let's create an empty MD file.
        md_file = tmp_path / "output.md"
        md_file.write_text("# Just text, no tables", encoding="utf-8")

        docs, count = processor.parse_tables(tmp_path, "test.pdf")
        # JSON has 1 table, MD has 0 -- JSON wins
        assert count == 1
        assert len(docs) == 1
        assert docs[0].metadata["table_id"] == "table_1_100"
        assert docs[0].metadata["table_json_id"] == 100

    def test_parse_tables_both_md_and_json(self, tmp_path):
        """MD and JSON both have tables -- MD content preferred."""
        processor = PDFProcessor()

        md_file = tmp_path / "output.md"
        md_file.write_text(
            "| Name | Value |\n|------|-------|\n| A | 1 |",
            encoding="utf-8",
        )

        data = _make_opendataloader_json([
            _make_table_entry(table_id=50, page=1, bbox=[0, 0, 500, 200]),
        ])
        json_file = tmp_path / "output.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        docs, count = processor.parse_tables(tmp_path, "report.pdf")
        assert count == 1
        assert "Name" in docs[0].page_content
        assert docs[0].metadata["document_name"] == "report.pdf"
        assert docs[0].metadata["table_id"] == "table_1_50"
        assert docs[0].metadata["bounding_box"] == [0, 0, 500, 200]

    def test_parse_tables_no_json_tables(self, tmp_path):
        """Returns empty when JSON has no table entries."""
        processor = PDFProcessor()

        md_file = tmp_path / "output.md"
        md_file.write_text(
            "| Name | Value |\n|------|-------|\n| A | 1 |",
            encoding="utf-8",
        )

        data = {"kids": [{"type": "heading", "content": "Title"}]}
        json_file = tmp_path / "output.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        docs, count = processor.parse_tables(tmp_path, "test.pdf")
        assert count == 0
        assert docs == []

    def test_parse_tables_md_fewer_than_json(self, tmp_path):
        """MD has fewer tables than JSON -- missing ones reconstructed."""
        processor = PDFProcessor()

        # MD with only 1 table
        md_file = tmp_path / "output.md"
        md_file.write_text(
            "| T1H |\n|-----|\n| A |",
            encoding="utf-8",
        )

        # JSON with 3 tables
        data = _make_opendataloader_json([
            _make_table_entry(table_id=100, page=1, num_rows=2, num_cols=1),
            _make_table_entry(table_id=200, page=2, num_rows=2, num_cols=1),
            _make_table_entry(table_id=300, page=3, num_rows=2, num_cols=1),
        ])
        json_file = tmp_path / "output.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        docs, count = processor.parse_tables(tmp_path, "test.pdf")
        assert count == 3
        # First table uses MD content
        assert "T1H" in docs[0].page_content
        # Second and third are reconstructed from JSON
        assert docs[1].metadata["table_json_id"] == 200
        assert docs[2].metadata["table_json_id"] == 300
        # Reconstructed tables should have content from JSON cells
        assert "H1" in docs[1].page_content

    def test_parse_tables_multiple_tables_match_order(self, tmp_path):
        """Verify that MD tables match JSON tables by sequential order."""
        processor = PDFProcessor()

        # MD with 3 tables
        md_file = tmp_path / "output.md"
        md_file.write_text(
            "| First |\n|-------|\n| 1 |\n\n"
            "text\n\n"
            "| Second |\n|--------|\n| 2 |\n\n"
            "text\n\n"
            "| Third |\n|-------|\n| 3 |",
            encoding="utf-8",
        )

        data = _make_opendataloader_json([
            _make_table_entry(table_id=10, page=1),
            _make_table_entry(table_id=20, page=2),
            _make_table_entry(table_id=30, page=3),
        ])
        json_file = tmp_path / "output.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        docs, count = processor.parse_tables(tmp_path, "test.pdf")
        assert count == 3
        assert "First" in docs[0].page_content
        assert docs[0].metadata["page_number"] == 1
        assert "Second" in docs[1].page_content
        assert docs[1].metadata["page_number"] == 2
        assert "Third" in docs[2].page_content
        assert docs[2].metadata["page_number"] == 3

    def test_parse_tables_with_real_hcs_data(self, tmp_path):
        """Integration test with actual hcs.json structure."""
        hcs_json = Path("output2/hcs/hcs.json")
        hcs_md = Path("output2/hcs/hcs.md")
        if not hcs_json.exists() or not hcs_md.exists():
            pytest.skip("hcs test data not available")

        import shutil
        shutil.copy(hcs_json, tmp_path / "hcs.json")
        shutil.copy(hcs_md, tmp_path / "hcs.md")
        # Copy images directory if it exists
        hcs_images = Path("output2/hcs/hcs_images")
        if hcs_images.exists():
            shutil.copytree(hcs_images, tmp_path / "hcs_images")

        processor = PDFProcessor()
        docs, count = processor.parse_tables(tmp_path, "hcs.pdf")

        assert count == 17
        assert len(docs) == 17

        # Verify first table metadata
        assert docs[0].metadata["page_number"] == 1
        assert docs[0].metadata["table_json_id"] == 872
        assert "유효등급" in docs[0].page_content

        # Verify all docs have required metadata fields
        for doc in docs:
            assert "page_number" in doc.metadata
            assert "bounding_box" in doc.metadata
            assert "table_id" in doc.metadata
            assert "table_json_id" in doc.metadata
            assert "document_name" in doc.metadata
            assert doc.metadata["document_name"] == "hcs.pdf"
            # bounding_box should always have 4 elements
            assert len(doc.metadata["bounding_box"]) == 4

    def test_parse_tables_no_json_file(self, tmp_path):
        """Returns empty when no JSON file exists."""
        processor = PDFProcessor()

        md_file = tmp_path / "output.md"
        md_file.write_text(
            "| Name | Value |\n|------|-------|\n| A | 1 |",
            encoding="utf-8",
        )

        # No JSON file
        docs, count = processor.parse_tables(tmp_path, "test.pdf")
        assert count == 0
        assert docs == []
