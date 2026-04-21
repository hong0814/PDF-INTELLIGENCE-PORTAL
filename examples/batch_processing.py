#!/usr/bin/env python3
"""
Batch multi-document table search example.

Usage:
    python batch_processing.py <pdf_path1> <pdf_path2> ... --query <query>

Example:
    python batch_processing.py ../test1.pdf ../test2.pdf --query "revenue growth"
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdftablesearch import search_tables


def progress_callback(current: int, total: int, filename: str, status: str) -> None:
    """Display progress during batch loading."""
    print(f"  [{current}/{total}] {filename}: {status}")


def main():
    parser = argparse.ArgumentParser(description="Search tables across multiple PDFs")
    parser.add_argument("pdfs", nargs="+", help="PDF file paths")
    parser.add_argument("--query", "-q", required=True, help="Search query")
    parser.add_argument("--max-per-doc", type=int, default=3, help="Max results per document")
    parser.add_argument("--max-total", type=int, default=20, help="Max total results")
    parser.add_argument("--rerank", action="store_true", help="Use LLM re-ranking")

    args = parser.parse_args()

    print(f"Searching for: '{args.query}'")
    print(f"Across {len(args.pdfs)} documents:")
    for pdf in args.pdfs:
        print(f"  - {pdf}")
    print("-" * 60)

    result = search_tables(
        pdf_path=args.pdfs,
        query=args.query,
        max_results=args.max_total,
        max_results_per_doc=args.max_per_doc,
        use_llm_rerank=args.rerank,
        progress_callback=progress_callback,
    )

    print(f"\nFound {result.total_results} tables across {len(result.document_counts)} documents")
    print(f"Per-document counts: {result.document_counts}")
    print()

    for doc_name, count in result.document_counts.items():
        print(f"== {doc_name} ({count} results) ==")
        doc_results = result.filter_by_document(doc_name)
        for i, table in enumerate(doc_results, 1):
            preview = table.table_markdown[:100].replace("\n", " | ")
            print(f"  {i}. {table.table_id} (page {table.page_number}): {preview}...")
        print()


if __name__ == "__main__":
    main()
