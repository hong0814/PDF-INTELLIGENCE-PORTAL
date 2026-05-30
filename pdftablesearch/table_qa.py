"""Table QA: answer natural language questions using search results and LLM.

Takes a search query, finds the most relevant table, and generates an
LLM-powered answer grounded in the table data.

Usage::

    from pdftablesearch.table_qa import ask_table

    answer = ask_table(
        query="2023년 매출이 가장 높은 사업부는?",
        pdf_path="report.pdf",
    )
    print(answer)
"""

from __future__ import annotations

from typing import Optional

from pdftablesearch.llm_client import ZaiLLMClient
from pdftablesearch.models import TableSearchResult
from pdftablesearch.smart_search import smart_search
from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

_QA_SYSTEM_PROMPT = """You are a financial data analyst assistant. \
Given a user question and an HTML table from a financial report, \
provide a clear, accurate answer in Korean.

Rules:
1. Answer based ONLY on the provided table data
2. Use specific numbers from the table when possible
3. If the table doesn't contain enough information, say so clearly
4. Keep answers concise (2-3 sentences max)
5. Respond in Korean
6. Do NOT include HTML tags in your answer. Use plain text or markdown tables only.
7. When presenting data, use markdown table format (| col1 | col2 |) instead of HTML."""

_QA_USER_PROMPT = """User Question: {query}

Table (HTML):
{table_html}

Table Title: {table_title}

Answer:"""


def ask_table(
    query: str,
    pdf_path: str,
    llm_model: str = "glm-4.7",
    api_key: Optional[str] = None,
    use_hybrid: bool = True,
    output_dir: Optional[str] = None,
    chroma_persist_dir: str = "./.chroma",
) -> str:
    """Answer a natural language question using the most relevant table.

    Combines smart_search (vector + LLM selection) with a final QA step
    that generates a natural language answer grounded in the table data.

    Args:
        query: Natural language question about the PDF content.
        pdf_path: Path to the PDF document.
        llm_model: LLM model name for QA generation.
        api_key: z.ai API key.
        use_hybrid: Whether to use hybrid PDF processing.
        output_dir: Optional output directory override.
        chroma_persist_dir: ChromaDB persistence directory.

    Returns:
        Generated answer string in Korean.
    """
    logger.info("Table QA: query='%s', pdf='%s'", query[:50], pdf_path)

    table = smart_search(
        query=query,
        pdf_path=pdf_path,
        top_k=10,
        llm_model=llm_model,
        api_key=api_key,
        use_hybrid=use_hybrid,
        output_dir=output_dir,
        chroma_persist_dir=chroma_persist_dir,
    )

    table_html = table.table_html or table.table_markdown or ""
    table_title = table.table_title or "(제목 없음)"

    client = ZaiLLMClient(api_key=api_key, model=llm_model)

    user_prompt = _QA_USER_PROMPT.format(
        query=query,
        table_html=table_html[:3000],
        table_title=table_title,
    )

    messages = [
        {"role": "system", "content": _QA_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response = client._llm.invoke(messages)
    answer = response.content if hasattr(response, "content") else str(response)

    logger.info("Table QA answer generated (%d chars)", len(answer))
    return answer
