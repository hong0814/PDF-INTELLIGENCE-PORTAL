#!/usr/bin/env python3
"""
Advanced LangChain integration demo.

Demonstrates how to use PDFTableSearch components directly with
LangChain primitives for custom pipelines.

Usage:
    python langchain_demo.py <pdf_path> <query>
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdftablesearch import PDFProcessor, ZaiEmbeddings, TableVectorStore
from pdftablesearch.models import TableSearchResult


def main():
    if len(sys.argv) < 3:
        print("Usage: python langchain_demo.py <pdf_path> <query>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    query = sys.argv[2]

    # Step 1: Initialize components
    print("Initializing components...")
    processor = PDFProcessor()
    embeddings = ZaiEmbeddings()  # Uses ZAI_API_KEY env variable

    # Step 2: Load PDF and extract tables
    print(f"Loading PDF: {pdf_path}")
    processing_result = processor.load_documents(pdf_path)
    print(f"  Extracted {processing_result.tables_extracted} tables")

    documents = processor.get_documents()

    if not documents:
        print("No tables found in the document.")
        return

    # Print extracted table metadata
    print("\nExtracted tables:")
    for doc in documents:
        meta = doc.metadata
        print(f"  - {meta['table_id']} (page {meta['page_number']})")
        print(f"    Preview: {doc.page_content[:80]}...")

    # Step 3: Build vector store
    print("\nBuilding vector index...")
    vector_store = TableVectorStore(
        embeddings=embeddings,
        persist_dir="./.chroma_demo",
        collection_name="demo_tables",
    )
    vector_store.add_documents(documents)

    stats = vector_store.get_stats()
    print(f"  Collection: {stats['collection_name']}")
    print(f"  Document count: {stats['document_count']}")

    # Step 4: Similarity search
    print(f"\nSearching for: '{query}'")
    results = vector_store.similarity_search(query=query, k=5)

    if not results:
        print("No matching tables found.")
        return

    print(f"\nFound {len(results)} results:\n")

    for i, (doc, score) in enumerate(results, 1):
        result = TableSearchResult.from_langchain_document(doc, score)
        print(f"[Result {i}] Score: {result.relevance_score:.4f}")
        print(f"  Table: {result.table_id} (page {result.page_number})")
        print(f"  Document: {result.document_name}")
        print(f"  Content:")
        for line in result.table_markdown.split("\n")[:5]:
            print(f"    {line}")
        if len(result.table_markdown.split("\n")) > 5:
            print("    ...")
        print()

    # Step 5: Search with metadata filter
    print("=" * 60)
    print("Filtered search (same document only):")
    doc_name = documents[0].metadata["document_name"]
    filtered = vector_store.similarity_search(
        query=query,
        k=3,
        filter_metadata={"document_name": doc_name},
    )
    print(f"  Found {len(filtered)} results in {doc_name}")


if __name__ == "__main__":
    main()
