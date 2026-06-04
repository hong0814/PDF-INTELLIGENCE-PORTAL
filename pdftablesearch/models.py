"""PDFTableSearch 데이터 모델.

검색, PDF 처리, 배치 처리를 위한 구조화된 결과 타입을 정의한다.
모든 모델은 JSON 직렬화를 지원하며 LangChain Document에서 생성할 수 있다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document


@dataclass
class TableSearchResult:
    """단일 표 검색 결과.

    HTML 형식의 표 내용과 소스 PDF 내 위치 메타데이터, 관련도 점수를 포함한다.

    속성:
        page_number: 표가 있는 페이지 번호 (0-indexed).
        bounding_box: 페이지 내 바운딩 박스 좌표 ``[x1, y1, x2, y2]``.
        table_html: 병합 셀(colspan/rowspan)을 보존하는 HTML 표.
        table_markdown: ``table_html``에서 파생된 마크다운 표현 (하위 호환).
        table_id: 고유 식별자 (예: ``"table_3_2"``).
        document_name: 소스 PDF 파일명.
        relevance_score: 벡터 검색 유사도 점수.
        rerank_score: LLM 리랭킹 점수.
        table_title: 문서에서 추출한 표 제목.
    """

    page_number: int
    bounding_box: List[int]
    table_html: str = ""
    table_markdown: str = ""
    table_id: str = ""
    document_name: str = ""
    relevance_score: Optional[float] = None
    rerank_score: Optional[float] = None
    table_title: Optional[str] = None
    table_type: Optional[str] = None
    group_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화 가능한 딕셔너리로 변환한다."""
        return {
            "page_number": self.page_number,
            "bounding_box": self.bounding_box,
            "table_html": self.table_html,
            "table_markdown": self.table_markdown,
            "table_id": self.table_id,
            "document_name": self.document_name,
            "relevance_score": self.relevance_score,
            "rerank_score": self.rerank_score,
            "table_title": self.table_title,
            "table_type": self.table_type,
            "group_id": self.group_id,
        }

    def to_json(self, indent: int = 2) -> str:
        """JSON 문자열로 직렬화한다."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TableSearchResult:
        """딕셔너리에서 인스턴스를 생성한다."""
        return cls(
            page_number=data.get("page_number", 0),
            bounding_box=data.get("bounding_box", []),
            table_html=data.get("table_html", ""),
            table_markdown=data.get("table_markdown", ""),
            table_id=data.get("table_id", ""),
            document_name=data.get("document_name", ""),
            relevance_score=data.get("relevance_score"),
            rerank_score=data.get("rerank_score"),
            table_title=data.get("table_title"),
            table_type=data.get("table_type"),
            group_id=data.get("group_id"),
        )

    @classmethod
    def from_langchain_document(
        cls, document: Document, score: float
    ) -> TableSearchResult:
        """LangChain Document와 유사도 점수에서 인스턴스를 생성한다.

        page_content에 제목 접두사가 있을 수 있으며, <table> 태그를
        찾아 table_html을 추출한다.
        """
        table_html = document.metadata.get("table_html", "")
        page_content = document.page_content

        if not table_html and page_content:
            stripped = page_content.strip()
            if stripped.startswith("<table") or stripped.startswith("<Table"):
                table_html = stripped
            else:
                table_start = page_content.find("<table")
                if table_start < 0:
                    table_start = page_content.find("<Table")
                if table_start >= 0:
                    table_html = page_content[table_start:]

        return cls(
            page_number=document.metadata.get("page_number", 0),
            bounding_box=document.metadata.get("bounding_box", []),
            table_html=table_html,
            table_markdown=page_content,
            table_id=document.metadata.get("table_id", ""),
            document_name=document.metadata.get("document_name", ""),
            relevance_score=score,
            table_title=document.metadata.get("table_title"),
            table_type=document.metadata.get("table_type"),
            group_id=document.metadata.get("group_id"),
        )


@dataclass
class MultiDocumentSearchResult:
    """다중 문서 검색 결과.

    여러 PDF 문서에 걸친 검색 결과를 문서별 통계와 함께 집계한다.

    속성:
        results: 모든 문서의 정렬된 검색 결과 목록.
        document_counts: 문서명 → 해당 문서에서 찾은 결과 수 매핑.
        total_results: 전체 결과 수.
        query: 원본 검색 쿼리 문자열.
    """

    results: List[TableSearchResult]
    document_counts: Dict[str, int] = field(default_factory=dict)
    total_results: int = 0
    query: str = ""

    def __post_init__(self) -> None:
        if not self.document_counts and self.results:
            counts: Dict[str, int] = {}
            for r in self.results:
                counts[r.document_name] = counts.get(r.document_name, 0) + 1
            self.document_counts = counts
        if self.total_results == 0 and self.results:
            self.total_results = len(self.results)

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화 가능한 딕셔너리로 변환한다."""
        return {
            "results": [r.to_dict() for r in self.results],
            "document_counts": self.document_counts,
            "total_results": self.total_results,
            "query": self.query,
        }

    def to_json(self, indent: int = 2) -> str:
        """JSON 문자열로 직렬화한다."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def filter_by_document(self, document_name: str) -> List[TableSearchResult]:
        """특정 문서에 속한 결과만 반환한다."""
        return [r for r in self.results if r.document_name == document_name]


@dataclass
class ProcessingResult:
    """단일 PDF 처리 결과.

    속성:
        documents_loaded: 생성된 LangChain Document 수.
        tables_extracted: PDF에서 찾은 표 수.
        document_name: 처리된 PDF 파일명.
    """

    documents_loaded: int
    tables_extracted: int
    document_name: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "documents_loaded": self.documents_loaded,
            "tables_extracted": self.tables_extracted,
            "document_name": self.document_name,
        }


@dataclass
class BatchProcessingResult:
    """배치 PDF 처리 결과.

    속성:
        successful: 오류 없이 처리된 파일의 :class:`ProcessingResult` 목록.
        failed: 파일명 → 오류 메시지 매핑.
        total_tables: 성공한 모든 파일에서 추출한 표 수 합계.
        total_documents: 처리한 전체 파일 수 (성공 + 실패).
    """

    successful: List[ProcessingResult]
    failed: Dict[str, str]
    total_tables: int = 0
    total_documents: int = 0

    def __post_init__(self) -> None:
        if self.total_tables == 0 and self.successful:
            self.total_tables = sum(s.tables_extracted for s in self.successful)
        if self.total_documents == 0:
            self.total_documents = len(self.successful) + len(self.failed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "successful": [r.to_dict() for r in self.successful],
            "failed": self.failed,
            "total_tables": self.total_tables,
            "total_documents": self.total_documents,
        }
