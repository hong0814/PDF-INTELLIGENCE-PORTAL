"""PDFTableSearch 커스텀 예외.

PDF 처리, 벡터 인덱싱, 검색 과정에서 발생하는 모든 오류 상황에 대한
구조화된 예외 계층을 제공한다.
"""


class TableSearchError(Exception):
    """표 검색 작업의 기본 예외.

    라이브러리의 모든 커스텀 예외가 이 클래스를 상속하므로,
    단일 except 절로 라이브러리 전체 예외를 catch할 수 있다.

    속성:
        message: 사람이 읽을 수 있는 오류 설명.
        details: 추가 오류 컨텍스트를 담은 선택적 딕셔너리.
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class PDFProcessingError(TableSearchError):
    """PDF 문서 처리 실패 시 발생.

    일반적인 원인:
        - 손상되거나 암호가 걸린 PDF
        - opendataloader-pdf 변환 실패
        - 잘못된 파일 형식
    """

    pass


class TableParsingError(TableSearchError):
    """변환 결과에서 표 내용을 파싱할 수 없을 때 발생.

    일반적인 원인:
        - PDF 변환 결과의 잘못된 마크다운 형식
        - 누락되거나 유효하지 않은 JSON 메타데이터
        - 예상과 다른 출력 형식
    """

    pass


class MetadataMismatchError(TableSearchError):
    """JSON 메타데이터와 마크다운 표 개수가 일치하지 않을 때 발생.

    PDF 변환기가 구조화된 메타데이터와 마크다운 콘텐츠 간에
    감지한 표 개수가 서로 다를 때 발생한다.
    """

    pass


class APIError(TableSearchError):
    """API 관련 오류의 기본 클래스.

    속성:
        status_code: 해당하는 HTTP 상태 코드.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict | None = None,
    ) -> None:
        self.status_code = status_code
        super().__init__(message, details)


class APIConnectionError(APIError):
    """API 엔드포인트 연결 실패 시 발생.

    일반적인 원인:
        - 네트워크 연결 문제
        - DNS 확인 실패
        - API 엔드포인트 접근 불가
        - 연결 타임아웃
    """

    pass


class APIAuthenticationError(APIError):
    """API 인증 실패 시 발생.

    일반적인 원인:
        - 잘못된 API 키
        - 만료된 API 키
        - API 키 누락
    """

    pass


class RateLimitError(APIError):
    """API 호출 한도 초과 시 발생.

    속성:
        retry_after: 재시도 전 대기 권장 시간(초).
    """

    def __init__(
        self,
        message: str = "API rate limit exceeded",
        retry_after: float | None = None,
        status_code: int | None = 429,
        details: dict | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code, details)


class VectorIndexError(TableSearchError):
    """벡터 인덱스 작업 실패 시 발생.

    일반적인 원인:
        - 임베딩 생성 실패
        - ChromaDB 초기화 실패
        - 문서 삽입 실패
    """

    pass


class VectorSearchError(TableSearchError):
    """벡터 유사도 검색 실패 시 발생.

    일반적인 원인:
        - 쿼리 임베딩 생성 실패
        - ChromaDB 쿼리 실패
        - 빈 인덱스 또는 손상된 인덱스
    """

    pass


class ResultFormattingError(TableSearchError):
    """검색 결과 포매팅 실패 시 발생.

    일반적인 원인:
        - 검색 결과에 필수 필드 누락
        - 호환되지 않는 메타데이터 형식
        - 직렬화 실패
    """

    pass
