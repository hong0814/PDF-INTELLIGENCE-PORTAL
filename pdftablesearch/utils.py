"""PDFTableSearch 공통 유틸리티.

로깅 설정, 환경변수 로드, 파일 검증, 경로 정리, 텍스트 헬퍼 등을 제공한다.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# 로깅
# ---------------------------------------------------------------------------

def get_logger(name: str, level: str | None = None) -> logging.Logger:
    """라이브러리용 설정된 로거를 생성한다.

    매개변수:
        name: 로거 이름 (보통 호출 모듈의 ``__name__``).
        level: 로깅 레벨 문자열 (예: ``"DEBUG"``, ``"INFO"``).
            미지정 시 ``LOG_LEVEL`` 환경변수 또는 ``"INFO"`` 사용.

    반환:
        설정된 :class:`logging.Logger` 인스턴스.
    """
    logger = logging.getLogger(name)

    effective_level = level or os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, effective_level, logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# ---------------------------------------------------------------------------
# 환경변수 헬퍼
# ---------------------------------------------------------------------------

def get_env(key: str, default: Any = None, required: bool = False) -> Any:
    """환경변수를 조회한다.

    매개변수:
        key: 환경변수 이름.
        default: 변수가 설정되지 않았을 때의 기본값.
        required: ``True``이면 변수가 누락되고 기본값도 없을 때
            :class:`ValueError` 발생.

    반환:
        환경변수 값 또는 *default*.

    예외:
        ValueError: *required*가 ``True``이고 변수가 없을 때.
    """
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(
            f"Required environment variable '{key}' is not set. "
            f"Please set it in your .env file or environment."
        )
    return value


def get_api_key(provided_key: str | None = None) -> str:
    """명시적 값 또는 환경변수에서 z.ai API 키를 해석한다.

    매개변수:
        provided_key: 명시적으로 제공된 API 키. 우선순위가 높다.

    반환:
        해석된 API 키 문자열.

    예외:
        ValueError: API 키를 찾을 수 없을 때.
    """
    key = provided_key or os.getenv("ZAI_API_KEY")
    if not key:
        raise ValueError(
            "z.ai API key is required. Provide it via the 'api_key' parameter "
            "or set the ZAI_API_KEY environment variable."
        )
    return key


# ---------------------------------------------------------------------------
# 파일 검증
# ---------------------------------------------------------------------------

_DEFAULT_MAX_FILE_SIZE_MB = 100


def validate_pdf_path(pdf_path: str, max_size_mb: int | None = None) -> Path:
    """PDF 파일이 존재하고 읽기 가능하며 크기 제한 내인지 검증한다.

    매개변수:
        pdf_path: PDF 파일 경로.
        max_size_mb: 최대 허용 파일 크기(MB).
            미지정 시 ``MAX_FILE_SIZE_MB`` 환경변수 또는 100.

    반환:
        해석된 :class:`Path` 객체.

    예외:
        FileNotFoundError: 파일이 존재하지 않을 때.
        ValueError: PDF가 아니거나 크기 제한 초과 시.
        PermissionError: 파일을 읽을 수 없을 때.
    """
    path = Path(pdf_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"File is not a PDF: {path}")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"PDF file is not readable: {path}")

    max_mb = max_size_mb or int(os.getenv("MAX_FILE_SIZE_MB", str(_DEFAULT_MAX_FILE_SIZE_MB)))
    file_size_mb = path.stat().st_size / (1024 * 1024)
    if file_size_mb > max_mb:
        raise ValueError(
            f"PDF file size ({file_size_mb:.1f} MB) exceeds the limit "
            f"of {max_mb} MB. Increase MAX_FILE_SIZE_MB if needed."
        )

    return path


def sanitize_path(path_str: str) -> Path:
    """디렉토리 순회 공격을 방지하기 위해 파일 경로를 정리한다.

    ``..`` 세그먼트를 제거하고 현재 작업 디렉토리에 대해 상대 경로를 해석한다.

    매개변수:
        path_str: 정리할 원시 경로 문자열.

    반환:
        정리된 :class:`Path` 객체.
    """
    cleaned = path_str.replace("\x00", "")
    resolved = Path(cleaned).resolve()

    if ".." in Path(cleaned).parts:
        raise ValueError(f"Path contains directory traversal: {path_str}")

    return resolved


# ---------------------------------------------------------------------------
# 재시도 설정
# ---------------------------------------------------------------------------

def get_retry_config() -> dict[str, Any]:
    """환경변수 또는 기본값에서 재시도 설정을 반환한다.

    반환:
        ``max_retries``, ``base_delay``, ``max_delay``, ``exponential_base`` 키를
        가진 딕셔너리. :mod:`tenacity`와 함께 사용.
    """
    return {
        "max_retries": int(os.getenv("RETRY_MAX_ATTEMPTS", "3")),
        "base_delay": float(os.getenv("RETRY_BASE_DELAY", "1.0")),
        "max_delay": float(os.getenv("RETRY_MAX_DELAY", "30.0")),
        "exponential_base": float(os.getenv("RETRY_EXPONENTIAL_BASE", "2.0")),
    }


# ---------------------------------------------------------------------------
# 텍스트 헬퍼
# ---------------------------------------------------------------------------

def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """텍스트를 최대 길이로 자른다. 초과 시 suffix를 붙인다."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def extract_table_context(markdown_content: str, max_rows: int = 3) -> str:
    """마크다운 표에서 임베딩용 컨텍스트 문자열을 추출한다.

    헤더 행과 최대 *max_rows*개의 데이터 행을 포함하여
    임베딩 품질과 토큰 예산의 균형을 맞춘다.

    매개변수:
        markdown_content: 전체 마크다운 표 문자열.
        max_rows: 포함할 최대 데이터 행 수.

    반환:
        임베딩에 적합한 압축된 표 컨텍스트.
    """
    lines = markdown_content.strip().split("\n")
    if not lines:
        return ""

    context_lines = [lines[0]]

    data_start = 1
    if len(lines) > 1 and re.match(r"^\|[\s\-:|]+\|$", lines[1].strip()):
        data_start = 2

    for line in lines[data_start : data_start + max_rows]:
        stripped = line.strip()
        if stripped and stripped.startswith("|"):
            context_lines.append(stripped)

    return "\n".join(context_lines)
