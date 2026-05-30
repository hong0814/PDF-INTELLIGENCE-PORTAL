"""Deterministic PII detection and masking helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from numbers import Number
from typing import Any

from bs4 import BeautifulSoup, NavigableString

PII_LABELS = {
    "resident_registration_number": "주민등록번호",
    "foreigner_registration_number": "외국인등록번호",
    "drivers_license_number": "운전면허번호",
    "passport_number": "여권번호",
    "vin": "차대번호",
    "vehicle_plate": "차량번호",
    "credit_card_number": "신용카드번호",
    "mobile_phone_number": "휴대전화번호",
    "landline_phone_number": "유선전화번호",
    "email_address": "이메일 주소",
}

HISTORY_REDACTED_USER_MESSAGE = "개인정보 포함된 문의"
_SPREADSHEET_CONTEXT_REQUIRED_TYPES = frozenset(
    {
        "resident_registration_number",
        "foreigner_registration_number",
        "drivers_license_number",
        "passport_number",
        "vin",
        "vehicle_plate",
        "credit_card_number",
    }
)
_SPREADSHEET_GENERIC_PII_CONTEXT_KEYWORDS = frozenset(
    {
        "pii",
        "privacy",
        "personalinfo",
        "personaldata",
        "personalinformation",
        "개인정보",
    }
)
_SPREADSHEET_PII_CONTEXT_KEYWORDS_BY_TYPE = {
    "resident_registration_number": frozenset(
        {"residentregistrationnumber", "residentnumber", "rrn", "주민등록번호", "주민번호"}
    ),
    "foreigner_registration_number": frozenset(
        {"foreignerregistrationnumber", "alienregistrationnumber", "arn", "외국인등록번호", "외국인번호"}
    ),
    "drivers_license_number": frozenset({"driverslicensenumber", "driverlicense", "운전면허번호", "면허번호"}),
    "passport_number": frozenset({"passportnumber", "passportno", "여권번호"}),
    "vin": frozenset({"vin", "vehicleidentificationnumber", "차대번호", "차량식별번호"}),
    "vehicle_plate": frozenset({"vehicleplate", "licenseplate", "carplate", "차량번호", "번호판"}),
    "credit_card_number": frozenset(
        {"creditcardnumber", "creditcard", "cardnumber", "cardno", "cardnum", "신용카드번호", "신용카드", "카드번호"}
    ),
}


@dataclass(frozen=True)
class PIIPattern:
    """탐지할 개인정보 유형 이름과 정규식을 묶는다."""

    name: str
    regex: re.Pattern[str]


@dataclass(frozen=True)
class PIIMatch:
    """Internal PII occurrence with source span information."""

    pii_type: str
    label: str
    value: str
    masked_value: str
    start: int
    end: int


@dataclass(frozen=True)
class PIIMaskResult:
    """PII detection result plus a masked text representation."""

    masked_text: str
    detections: list[dict[str, str]]

    @property
    def has_pii(self) -> bool:
        return bool(self.detections)


# 탐지 대상만 정의하고, 흐름 제어는 호출 측에서 처리한다.
PATTERNS: tuple[PIIPattern, ...] = (
    PIIPattern("resident_registration_number", re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)")),
    PIIPattern("foreigner_registration_number", re.compile(r"(?<!\d)\d{6}[- ]?[5-8]\d{6}(?!\d)")),
    PIIPattern("drivers_license_number", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{5}(?!\d)")),
    PIIPattern("passport_number", re.compile(r"(?<![A-Z0-9])[A-Z]{1,2}\d{7,8}(?![A-Z0-9])")),
    PIIPattern("vin", re.compile(r"(?<![A-HJ-NPR-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-HJ-NPR-Z0-9])")),
    PIIPattern("credit_card_number", re.compile(r"(?<!\d)\d{4}-\d{4}-\d{4}-\d{4}(?!\d)")),
    PIIPattern("mobile_phone_number", re.compile(r"(?<!\d)01[016789][ -]?\d{2,4}[ -]?\d{3,4}(?!\d)")),
    PIIPattern(
        "landline_phone_number",
        re.compile(r"(?<!\d)(?:02|0[3-6][1-5]|070|050[2-8])[ -]?\d{3,4}[ -]?\d{4}(?!\d)"),
    ),
    PIIPattern(
        "email_address",
        re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    ),
)


def _mask_keep_edges(value: str, left: int, right: int) -> str:
    """문자열 양 끝 일부만 남기고 중간을 마스킹한다."""
    if len(value) <= left + right:
        return "*" * len(value)
    masked_len = len(value) - left - right
    suffix = value[-right:] if right else ""
    return f"{value[:left]}{'*' * masked_len}{suffix}"


def _mask_digits(value: str, left_digits: int, right_digits: int) -> str:
    """숫자만 기준으로 앞/뒤 일부를 남기고 형식은 유지한 채 마스킹한다."""
    total_digits = sum(char.isdigit() for char in value)
    if total_digits == 0:
        return _mask_keep_edges(value, 1, 1)

    keep_until = left_digits
    keep_from = max(total_digits - right_digits, left_digits)
    current_digit = 0
    masked: list[str] = []

    for char in value:
        if not char.isdigit():
            masked.append(char)
            continue

        current_digit += 1
        if current_digit <= keep_until or current_digit > keep_from:
            masked.append(char)
        else:
            masked.append("*")

    return "".join(masked)


def _mask_email(value: str) -> str:
    """이메일은 로컬 파트와 도메인을 각각 축약 마스킹한다."""
    local, _, domain = value.partition("@")
    if not local or not domain:
        return _mask_keep_edges(value, 1, 1)

    masked_local = _mask_keep_edges(local, 1, 0)
    domain_name, dot, suffix = domain.rpartition(".")
    if not dot:
        return f"{masked_local}@{_mask_keep_edges(domain, 1, 0)}"

    return f"{masked_local}@{_mask_keep_edges(domain_name, 1, 0)}.{suffix}"


def _mask_value(name: str, value: str) -> str:
    """개인정보 유형별로 최소한의 식별 단서만 남기는 마스킹 문자열을 만든다."""
    if name in {"mobile_phone_number", "landline_phone_number"}:
        return _mask_digits(value, left_digits=3, right_digits=2)
    if name in {
        "resident_registration_number",
        "foreigner_registration_number",
        "drivers_license_number",
        "credit_card_number",
    }:
        return _mask_digits(value, left_digits=2, right_digits=2)
    if name == "email_address":
        return _mask_email(value)
    if name in {"passport_number", "vin"}:
        return _mask_keep_edges(value, 2, 2)
    if name == "vehicle_plate":
        return _mask_keep_edges(value, 0, 2)
    return _mask_keep_edges(value, 1, 1)


def _overlaps(start: int, end: int, selected: list[PIIMatch]) -> bool:
    return any(start < current.end and current.start < end for current in selected)


def _detect_pii_matches(text: str, *, dedupe_values: bool = True) -> list[PIIMatch]:
    """입력 문자열에서 중복/중첩을 제거한 PII span을 수집한다."""
    matches: list[PIIMatch] = []
    seen: set[tuple[str, str]] = set()

    for pattern in PATTERNS:
        for match in pattern.regex.finditer(text):
            start, end = match.span()
            if _overlaps(start, end, matches):
                continue

            value = match.group(0)
            dedupe_key = (pattern.name, value)
            if dedupe_values and dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            matches.append(
                PIIMatch(
                    pii_type=pattern.name,
                    label=PII_LABELS.get(pattern.name, pattern.name),
                    value=value,
                    masked_value=_mask_value(pattern.name, value),
                    start=start,
                    end=end,
                )
            )

    return sorted(matches, key=lambda item: item.start)


def _match_to_detection(match: PIIMatch) -> dict[str, str]:
    return {
        "type": match.pii_type,
        "label": match.label,
        "value": match.value,
        "masked_value": match.masked_value,
    }


def detect_pii(text: str) -> list[dict[str, str]]:
    """입력 문자열에서 정책상 차단할 개인정보 후보를 중복 없이 수집한다."""
    return [_match_to_detection(match) for match in _detect_pii_matches(str(text or ""))]


def _is_numeric_cell_value(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, Number)


def _normalize_spreadsheet_context(value: Any) -> str:
    return (
        str(value or "").casefold().replace(" ", "").replace("_", "").replace("-", "").replace("/", "").replace(".", "")
    )


def _spreadsheet_context_allows_detection(detection: dict[str, str], *, context_values: list[Any]) -> bool:
    detection_type = str(detection.get("type") or "")
    keywords = _SPREADSHEET_GENERIC_PII_CONTEXT_KEYWORDS | _SPREADSHEET_PII_CONTEXT_KEYWORDS_BY_TYPE.get(
        detection_type,
        frozenset(),
    )
    normalized_context = " ".join(_normalize_spreadsheet_context(value) for value in context_values)
    return any(keyword in normalized_context for keyword in keywords)


def _should_keep_spreadsheet_detection(
    detection: dict[str, str],
    *,
    value: Any,
    context_values: list[Any],
) -> bool:
    detection_type = str(detection.get("type") or "")
    if detection_type not in _SPREADSHEET_CONTEXT_REQUIRED_TYPES or not _is_numeric_cell_value(value):
        return True
    return _spreadsheet_context_allows_detection(detection, context_values=context_values)


def detect_pii_in_spreadsheet_cell(value: Any, *, context_values: list[Any] | tuple[Any, ...]) -> list[dict[str, str]]:
    """스프레드시트 셀 값의 PII 후보를 주변 라벨/헤더 맥락으로 필터링해 반환한다."""
    detections = detect_pii(str(value))
    return [
        detection
        for detection in detections
        if _should_keep_spreadsheet_detection(detection, value=value, context_values=list(context_values))
    ]


def mask_pii_text(text: str) -> str:
    """입력 문자열의 PII 원문을 유형별 마스킹 값으로 치환한다."""
    source = str(text or "")
    matches = _detect_pii_matches(source, dedupe_values=False)
    if not matches:
        return source

    masked = source
    for match in sorted(matches, key=lambda item: item.start, reverse=True):
        masked = f"{masked[: match.start]}{match.masked_value}{masked[match.end :]}"
    return masked


def check_and_mask_pii(text: str) -> PIIMaskResult:
    """PII 탐지 결과와 마스킹된 텍스트를 함께 반환한다."""
    source = str(text or "")
    matches = _detect_pii_matches(source, dedupe_values=False)
    if not matches:
        return PIIMaskResult(masked_text=source, detections=[])
    masked_text = source
    for match in sorted(matches, key=lambda item: item.start, reverse=True):
        masked_text = f"{masked_text[: match.start]}{match.masked_value}{masked_text[match.end :]}"
    return PIIMaskResult(
        masked_text=masked_text,
        detections=[_match_to_detection(match) for match in matches],
    )


def sanitize_user_message_for_history(text: str) -> tuple[str, list[dict[str, str]]]:
    """히스토리/메모리에는 개인정보 원문 대신 일반화 문구만 남긴다."""
    detections = detect_pii(text)
    if not detections:
        return text, []
    return HISTORY_REDACTED_USER_MESSAGE, detections


def mask_pii_in_data(value: Any) -> Any:
    """Nested file-analysis data에서 PII scalar 값을 재귀적으로 마스킹한다."""
    if isinstance(value, dict):
        return {key: mask_pii_in_data(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [mask_pii_in_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_pii_in_data(item) for item in value)
    if isinstance(value, str):
        return mask_pii_text(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        result = check_and_mask_pii(str(value))
        return result.masked_text if result.has_pii else value
    return value


# ---------------------------------------------------------------------------
# HTML-specific PII masking (for table_html fields)
# ---------------------------------------------------------------------------

def mask_pii_in_html(html: str) -> str:
    """HTML 문자열에서 텍스트 노드만 순회하며 PII를 마스킹한다.

    태그/속성은 건드리지 않고 ``<td>`` 등 안의 텍스트만 마스킹.
    """
    if not html or "<" not in html:
        return mask_pii_text(html)

    soup = BeautifulSoup(html, "html.parser")

    for text_node in soup.find_all(string=True):
        if not isinstance(text_node, NavigableString):
            continue
        original = str(text_node)
        if not original.strip():
            continue
        masked = mask_pii_text(original)
        if masked != original:
            text_node.replace_with(NavigableString(masked))

    return str(soup)
