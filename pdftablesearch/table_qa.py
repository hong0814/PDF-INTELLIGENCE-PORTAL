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
    persist_dir: str = "./.chroma",
) -> str:
    """가장 관련성 높은 표를 활용하여 자연어 질문에 답변한다.

    smart_search(벡터 + LLM 선택)와 최종 QA 단계를 결합하여
    표 데이터에 근거한 자연어 답변을 생성한다.

    매개변수:
        query: PDF 내용에 대한 자연어 질문.
        pdf_path: PDF 문서 경로.
        llm_model: QA 생성용 LLM 모델명.
        api_key: z.ai API 키.
        use_hybrid: 하이브리드 PDF 처리 사용 여부.
        output_dir: 출력 디렉토리 오버라이드.
        persist_dir: 벡터 스토어 데이터 디렉토리.

    반환:
        한국어 답변 문자열.
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
        persist_dir=persist_dir,
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
