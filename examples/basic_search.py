#!/usr/bin/env python3
"""
Basic single-document table search example.

Usage:
    python basic_search.py <pdf_path> <query>

Example:
    python basic_search.py ../test1.pdf "quarterly revenue"
"""

import sys
import os

# Add parent directory to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdftablesearch import search_tables, TableSearchResult


def main():
    if len(sys.argv) < 3:
        print("Usage: python basic_search.py <pdf_path> <query>")
        print('Example: python basic_search.py report.pdf "financial summary"')
        sys.exit(1)

    pdf_path = sys.argv[1]
    query = sys.argv[2]

    print(f"Searching for: '{query}'")
    print(f"In file: {pdf_path}")
    print("-" * 60)

    results = search_tables(
        pdf_path=pdf_path,
        query=query,
        max_results=5,
        use_llm_rerank=False,
    )

    if not results:
        print("No matching tables found.")
        return

    print(f"Found {len(results)} matching tables:\n")

    for i, result in enumerate(results, 1):
        print(f"[Result {i}]")
        print(f"  Table ID: {result.table_id}")
        print(f"  Page: {result.page_number}")
        print(f"  Document: {result.document_name}")
        print(f"  Score: {result.relevance_score:.4f}")
        if result.rerank_score is not None:
            print(f"  Rerank Score: {result.rerank_score:.4f}")
        print(f"  Content (preview):")
        preview = result.table_markdown[:200]
        for line in preview.split("\n"):
            print(f"    {line}")
        if len(result.table_markdown) > 200:
            print("    ...")
        print()


if __name__ == "__main__":
    main()
