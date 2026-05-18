"""
Command-line interface for smart table search.

Provides a CLI for testing the :func:`smart_search` function with
various configuration options.

Usage::

    python -m pdftablesearch.smart_search_cli \\
        --pdf test2.pdf \\
        --query "포괄손익계산서" \\
        --top-k 20 \\
        --llm-model glm-5.1
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

from pdftablesearch.models import TableSearchResult
from pdftablesearch.smart_search import smart_search
from pdftablesearch.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _format_result(
    result: TableSearchResult,
    query: str,
    pdf_path: str,
    elapsed: float,
    llm_success: bool,
) -> str:
    """Format a smart search result into a human-readable string.

    Args:
        result: The selected table result.
        query: Original search query.
        pdf_path: Path to the PDF file.
        elapsed: Total elapsed time in seconds.
        llm_success: Whether LLM selection succeeded.

    Returns:
        Formatted output string.
    """
    lines: list[str] = []

    lines.append("=" * 60)
    lines.append("  Smart Search Results")
    lines.append("=" * 60)
    lines.append(f"  Query: {query}")
    lines.append(f"  PDF:   {pdf_path}")
    lines.append(f"  Time:  {elapsed:.2f}s")
    lines.append(f"  Mode:  {'LLM Selection' if llm_success else 'Vector Fallback'}")
    lines.append("")

    # Selection status
    if llm_success:
        lines.append("  [OK] Best Match Found (LLM selected):")
    else:
        lines.append("  [FALLBACK] Best Match from Vector Search:")

    lines.append(f"    Table ID:    {result.table_id}")
    lines.append(f"    Page:        {result.page_number}")
    lines.append(f"    Title:       {result.table_title or '(No title)'}")
    lines.append(f"    Document:    {result.document_name}")
    lines.append(f"    Vec Score:   {result.relevance_score}")

    if result.rerank_score is not None:
        lines.append(f"    LLM Score:   {result.rerank_score}")

    lines.append("")
    lines.append("  Preview:")

    # Content preview (first 5 lines)
    if result.table_markdown:
        md_lines = result.table_markdown.split("\n")
        preview_lines = md_lines[:5]
        for line in preview_lines:
            lines.append(f"    {line}")
        if len(md_lines) > 5:
            lines.append(f"    ... ({len(md_lines) - 5} more lines)")
    else:
        lines.append("    (No content)")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="smart_search_cli",
        description=(
            "Smart table search: combines vector similarity search "
            "with LLM re-ranking for precise table identification."
        ),
    )

    parser.add_argument(
        "--pdf",
        type=str,
        required=True,
        help="Path to the PDF file to search.",
    )

    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Natural language search query (Korean or English).",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of vector search candidates (default: 20).",
    )

    parser.add_argument(
        "--llm-model",
        type=str,
        default="glm-4.7",
        help="LLM model name (default: glm-4.7).",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="z.ai API key (falls back to ZAI_API_KEY env var).",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Override PDF conversion output directory.",
    )

    parser.add_argument(
        "--chroma-dir",
        type=str,
        default="./.chroma",
        help="ChromaDB persistence directory (default: ./.chroma).",
    )

    parser.add_argument(
        "--no-hybrid",
        action="store_true",
        default=False,
        help="Disable hybrid PDF processing mode.",
    )

    parser.add_argument(
        "--no-fallback",
        action="store_true",
        default=False,
        help="Raise error instead of falling back to vector search on LLM failure.",
    )

    parser.add_argument(
        "--json-output",
        action="store_true",
        default=False,
        help="Output result as JSON instead of human-readable format.",
    )

    return parser


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> None:
    """CLI entry point for smart table search.

    Args:
        argv: Command-line arguments. Defaults to ``sys.argv[1:]``.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    start_time = time.time()

    try:
        result = smart_search(
            query=args.query,
            pdf_path=args.pdf,
            top_k=args.top_k,
            llm_model=args.llm_model,
            api_key=args.api_key,
            use_hybrid=not args.no_hybrid,
            output_dir=args.output_dir,
            fallback_to_vector=not args.no_fallback,
            chroma_persist_dir=args.chroma_dir,
        )
        elapsed = time.time() - start_time

        # Determine if LLM succeeded (has rerank_score) vs fallback
        llm_success = result.rerank_score is not None

        if args.json_output:
            print(result.to_json())
        else:
            output = _format_result(
                result=result,
                query=args.query,
                pdf_path=args.pdf,
                elapsed=elapsed,
                llm_success=llm_success,
            )
            print(output)

    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        logger.exception("Smart search failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
