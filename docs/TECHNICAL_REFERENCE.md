# PDF Intelligence Portal — 기술 레퍼런스

> 금융 문서(신용심사, PF대출, 재무제표 등)를 업로드하고 자연어로 검색하는 AI 기반 문서 분석 포털의
> 전체 기술 아키텍처를 계층별·모듈별로 상세히 기술한다.

---

## 목차

1. [시스템 전체 구조](#1-시스템-전체-구조)
2. [PDF 파싱 파이프라인 (계층적 처리)](#2-pdf-파싱-파이프라인-계층적-처리)
3. [표(Table) 처리 엔진](#3-표table-처리-엔진)
4. [임베딩 & 벡터 DB (Weaviate)](#4-임베딩--벡터-db-weaviate)
5. [검색 아키텍처](#5-검색-아키텍처)
6. [RAG 파이프라인](#6-rag-파이프라인)
7. [인증 (LDAP + JWT)](#7-인증-ldap--jwt)
8. [PII 마스킹](#8-pii-마스킹)
9. [세션 관리](#9-세션-관리)
10. [API 레퍼런스](#10-api-레퍼런스)
11. [프론트엔드 아키텍처](#11-프론트엔드-아키텍처)
12. [폐쇄망 배포](#12-폐쇄망-배포)
13. [환경 변수 전체 목록](#13-환경-변수-전체-목록)

---

## 1. 시스템 전체 구조

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Browser (React 19)                           │
│  Zustand · Tailwind v4 · pdf.js · react-markdown                   │
└──────────────┬──────────────────────────────────────────────────────┘
               │ HTTP / SSE
┌──────────────▼──────────────────────────────────────────────────────┐
│                     FastAPI (:8000)                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │ auth.py  │ │ upload   │ │ search   │ │ qa       │               │
│  │ LDAP+JWT │ │ pipeline │ │ pipeline │ │ pipeline │               │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │
└────┬──────────┬──────────┬──────────┬───────────────────────────────┘
     │          │          │          │
     ▼          ▼          ▼          ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────┐
│ LDAP    │ │ Weaviate│ │ Ollama  │ │ opendataloader-  │
│ :3890   │ │ :8079   │ │ Cloud   │ │ pdf :5002        │
│         │ │ (embed) │ │ gpt-oss │ │ docling-fast     │
└─────────┘ └─────────┘ └─────────┘ └──────────────────┘
                 │
           ┌─────┴──────┐
           │ bge-m3     │
           │ 임베딩(CPU) │
           └────────────┘
```

### 기술 스택

| 계층 | 기술 |
|------|------|
| **프론트엔드** | React 19, TypeScript, Tailwind CSS v4, Zustand 5, pdf.js 4.0 |
| **백엔드** | FastAPI, Uvicorn, LangChain |
| **인증** | LDAP (ldap3), JWT (PyJWT), httpOnly 쿠키 |
| **벡터 DB** | Weaviate 1.30+ (Embedded) |
| **임베딩** | SentenceTransformers (BAAI/bge-m3, 1024차원, CPU) |
| **LLM** | Ollama Cloud (gpt-oss:120b) |
| **PDF 처리** | opendataloader-pdf (docling-fast), PyMuPDF (fitz), BeautifulSoup4 |
| **검색** | BM25Okapi (rank-bm25), RRF Fusion |
| **보안** | PII 마스킹 (주민/계좌/전화번호), CORS |

---

## 2. PDF 파싱 파이프라인 (계층적 처리)

PDF 업로드 시 **다중 포맷 병렬 변환 → 크로스 매칭 → 계층적 Document 생성**의 3단계로 처리한다.

### 2.1 전체 흐름

```
PDF 파일
   │
   ├── opendataloader-pdf (hybrid: docling-fast)
   │      ├── *.html   ← 표 HTML + 페이지 구조
   │      ├── *.json   ← 표 메타데이터 (bbox, 행/열)
   │      └── *.md     ← 표 제목 + 문맥
   │
   ├── 표준 변환 (standard)
   │      └── *.html   ← 중첩 표 포함 HTML
   │
   └── PyMuPDF (fitz)
          └── 표 감지 + bbox + 데이터 추출
                │
                ▼
┌─────────────────────────────────────────────┐
│          _build_tables_from_pymupdf()        │
│  ┌─────────┐   매칭    ┌──────────────────┐ │
│  │ PyMuPDF │ ◄────────► │ Hybrid HTML/JSON │ │
│  │ 표 목록 │  Jaccard   │ 표 목록          │ │
│  └─────────┘  + Y축     └──────────────────┘ │
│       │        중첩                           │
│       ▼                                      │
│  통합 표 리스트 (results)                      │
│  - outer 표 + inner 표                        │
│  - hybrid_table_id 이중 매칭                  │
└─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────┐
│        extract_table_structure()             │
│  full_table Document                         │
│  + cell_chunk Documents (계층적)             │
└─────────────────────────────────────────────┘
                │
                ▼
      Weaviate + BM25 인덱싱
```

### 2.2 1단계: 다중 포맷 변환 (`PDFProcessor.convert_pdf()`)

**파일**: `pdftablesearch/loader/__init__.py`

opendataloader-pdf를 통해 PDF를 3가지 포맷으로 동시 변환한다.

```python
convert_params = {
    "input_path": str(pdf_path),
    "output_dir": str(output_dir),
    "format": "html, json, markdown",
    "hybrid": "docling-fast",           # 하이브리드 모드 활성화
    "hybrid_url": "http://localhost:5002",  # docling-fast 서버
}
```

| 포맷 | 역할 | 출력 파일 |
|------|------|----------|
| **HTML** | 표 콘텐츠 (렌더링 가능한 `<table>` 태그) | `*.html` |
| **JSON** | 정확한 bbox(좌표), 행/열 구조, 셀 데이터 | `*.json` |
| **Markdown** | 표 제목, 주변 문맥 텍스트 | `*.md` |

하이브리드 서버(`docling-fast`)가 응답하지 않으면 자동으로 표준 변환으로 폴백한다.

### 2.3 2단계: 크로스 소스 매칭

각 파서가 독립적으로 데이터를 추출하고, Matcher가 이를 연결한다.

#### JSON 파서 (`loader/json_parser.py`)

opendataloader-pdf JSON 출력에서 **정확한 기하 정보**를 추출한다.

```python
# 출력 스키마
{
    "page_number": int,        # 페이지 번호 (1-based)
    "bounding_box": [x1, y1, x2, y2],  # PDF 좌표 (좌하단 원점)
    "index": int,
    "id": int,                 # 고유 테이블 ID
    "table_data": {
        "rows": [...],         # 셀 데이터
        "num_cols": int
    }
}
```

> **중요**: docling/opendataloader-pdf의 bbox는 이미 PDF 좌표계(좌하단 원점, Y축 위쪽)이다. 추가 변환 금지.

#### HTML 파서 (`loader/html_parser.py`)

HTML에서 `<table>` 요소를 추출하고 정제한다.

| 함수 | 역할 |
|------|------|
| `extract_html_tables_from_file()` | `<table>` 추출 + 이전 헤더를 title로 캡처 |
| `extract_table_text_content()` | 텍스트 정규화 (매칭용) |
| `sanitize_table_html()` | script, 이벤트 핸들러 제거 |
| `html_table_to_markdown()` | HTML → Markdown 변환 (colspan/rowspan 지원) |

#### Markdown 파서 (`loader/markdown_parser.py`)

Markdown에서 표 제목과 문맥을 추출한다.

- 각 표 앞 15줄을 스캔하여 제목 후보 탐색
- 헤더(`#`, `##`), 리스트, 꺾쇠 괄호(`<...>`) 형식 지원
- 표 분포 기반으로 페이지 번호 추정
- 문맥 텍스트는 300자로 제한

#### Matcher (`loader/matcher.py`)

HTML 표와 JSON 메타데이터를 **Jaccard 유사도**로 연결한다.

```python
def find_best_json_match(html_text, json_metadata, used_indices):
    # 1. 텍스트 정규화 (소문자, 공백 제거)
    # 2. Jaccard 단어 교집합 유사도 계산
    # 3. 임계값 0.3 이상만 허용
    # 4. 중복 매칭 방지 (used_indices)
```

### 2.4 3단계: 계층적 Document 생성 (`load_documents()`)

매칭된 데이터로 LangChain Document를 생성한다. **1개 표 = 1개 full_table + N개 cell_chunk**.

```python
# full_table Document
Document(
    page_content=structured_text,    # "경로 > 키 : 값" 형식의 전체 텍스트
    metadata={
        "doc_type": "full_table",
        "table_id": "table_5_123",
        "page_number": 5,
        "bounding_box": [72.3, 80.1, 560.5, 450.2],
        "table_html": "<table>...</table>",
        "table_title": "재무상태표",
        "table_context": "...",
        "document_name": "annual_report",
    }
)

# cell_chunk Documents (표의 각 필드)
Document(
    page_content="재무상태표 > 자산총계 : 1,234,567",
    metadata={
        "doc_type": "cell_chunk",
        "parent_table_id": "table_5_123",
        "chunk_index": 3,
        "hierarchy_path": "재무상태표 > 자산총계",
        "key_field": "자산총계",
        "depth": 1,
    }
)
```

**필드 경로 포맷**: `표제목 > 대분류 > 소분류 : 셀값`

이 계층 구조 덕분에 "삼성생명의 임대면적은?" 같은 질의에서 cell_chunk가 정확히 매칭된다.

---

## 3. 표(Table) 처리 엔진

### 3.1 하이브리드 표 구축 (`_build_tables_from_pymupdf()`)

**파일**: `pdftablesearch/table_utils.py` (라인 242~508)

PyMuPDF 표 감지 결과와 Hybrid HTML/JSON 결과를 융합하여 최종 표 리스트를 생성한다.

#### 처리 순서

```
1. PyMuPDF로 모든 페이지에서 표 감지
   - page.find_tables().tables
   - 면적 < 5000인 표 필터링 (노이즈 제거)
   - PyMuPDF bbox → PDF bbox 변환:
     pdf_bbox = [fbbox[0], page_h - fbbox[3], fbbox[2], page_h - fbbox[1]]

2. Inner 표 감지 (bbox 포함 관계)
   - bbox_i가 bbox_j 안에 완전히 포함되면 inner로 분류
   - 조건: b2[0]≤b1[0] ∧ b2[1]≤b1[1] ∧ b2[2]≥b1[2] ∧ b2[3]≥b1[3]

3. 3단계 매칭 (우선순위: standard → hybrid → PyMuPDF)
   ┌─────────────────────────────────────────────────┐
   │ Step 1: Standard HTML 매칭 (inner 표 있는 경우) │
   │   - 중첩 표 포함 HTML과 텍스트 Jaccard 매칭    │
   │   - 임계값 > 0.10                               │
   ├─────────────────────────────────────────────────┤
   │ Step 2: Hybrid HTML/JSON 매칭                   │
   │   - 텍스트 Jaccard × (0.5 + 0.5 × Y축 중첩비)  │
   │   - Y축 중첩 = 겹침 / min(높이A, 높이B)        │
   │   - 임계값 > 0.10                               │
   ├─────────────────────────────────────────────────┤
   │ Step 3: PyMuPDF fallback                        │
   │   - fitz 데이터로 <table> 직접 생성             │
   │   - 최후 수단                                   │
   └─────────────────────────────────────────────────┘

4. Inner 표의 Hybrid 매칭 (50% 면적 중첩)
   - PyMuPDF inner bbox와 Hybrid bbox의 면적 중첩 비율 > 0.5이면 Hybrid 우선

5. 미매칭 Hybrid 표 추가 (fallback)
   - 이미 outer/inner로 포함된 Hybrid 표는 제외
```

#### 최종 표 엔트리 스키마

```python
{
    "table_id": "fitz_p5_2",           # PyMuPDF 기반 ID
    "hybrid_table_id": "table_5_123",  # Hybrid HTML/JSON ID (이중 매칭)
    "page_number": 5,
    "bounding_box": [x0, y0, x1, y1],  # PDF 좌표 (좌하단 원점)
    "table_html": "<table>...</table>",
    "table_title": "투자비용",
    "sub_title": "투자비용\n(단위: 억원)",    # 표 상단 텍스트 (최대 3줄)
    "document_name": "busan",
    "has_inner_tables": True,
    "is_inner": False,
    "outer_table_id": None,
    "inner_table_ids": ["fitz_p5_2_inner1"],
    "_source": "hybrid" | "standard" | "pymupdf" | "hybrid_fallback"
}
```

#### 좌표계

| 시스템 | 원점 | Y축 | 변환 |
|--------|------|-----|------|
| **PyMuPDF** | 좌상단 | ↓ 아래로 | 원본 |
| **PDF 표준** | 좌하단 | ↑ 위쪽 | `y_new = page_h - y_old` |
| **opendataloader** | 좌하단 | ↑ 위쪽 | 변환 불필요 (이미 PDF coords) |
| **프론트엔드(Viewport)** | 좌상단 | ↓ 아래로 | `viewport.convertToViewportPoint()` |

```
PDF 좌표계:              프론트엔드 Viewport:
┌──────────┐ y=page_h   ┌──────────┐ y=0
│  (0,H)   │            │  (0,0)   │
│          │            │          │
│  원점    │            │  원점    │
│  (0,0)   │            │  (0,H)   │
└──────────┘ y=0        └──────────┘ y=page_h
```

### 3.2 다중 페이지 표 감지 (`_detect_multipage_tables()`)

**파일**: `pdftablesearch/table_utils.py` (라인 511~650)

연속 페이지에 걸친 표를 자동 감지하여 그룹화한다.

#### 알고리즘

```
1. 연속 페이지 쌍 탐색 (pa, pb = pa+1)

2. 페이지 A의 "하단 근처" 표 탐색
   - bbox_y0 < 200 (PDF coords: 표가 페이지 하단에 있음)

3. 페이지 B의 "상단 근처" 표 탐색
   - bbox_y1 > 400 (PDF coords: 표가 페이지 상단에 있음)

4. 열(Column) 일치 검증
   - HTML에서 열 수 계산: _table_col_count()
   - same_cols = (cols_a == cols_b && cols_a > 0)
   - 열이 다르지만 표가 페이지 최상단(bbox_y1 > 700)이면 강제 포함

5. 추이적 폐포 (Transitive Closure)
   - A→B, B→C 감지 시 → [A, B, C] 체인 생성
   - Union-Find 방식으로 체인 병합
   - 최종: 길이 ≥ 2인 체인만 반환
```

#### 그룹화 결과

```python
{
    "group_id": "group_0",
    "tables": [
        {"table_id": "fitz_p1_0", "page_number": 1, "bounding_box": [...], ...},
        {"table_id": "fitz_p2_0", "page_number": 2, "bounding_box": [...], ...},
        ...
    ],
    "chain_length": 9,
    "same_cols": True,
    "pair_cols": [(True, 6, 6), (True, 6, 6), ...]  # 각 쌍별 열 일치 여부
}
```

### 3.3 표 병합 (`_merge_grouped_tables()`)

사용자가 그룹을 확인하면, 체인의 표 HTML을 하나로 병합한다.

- 첫 번째 표의 `<table>`을 베이스로 사용
- 이후 표의 행을 추가 (헤더 행은 중복 스킵)
- `group_id`, `merged_table_html`, `group_table_ids` 필드 설정

---

## 4. 임베딩 & 벡터 DB (Weaviate)

### 4.1 임베딩 파이프라인

**임베딩 모델**: BAAI/bge-m3 (1024차원, 다국어 지원, CPU)

```
                        ┌─────────────────────┐
                        │ create_embeddings()  │
                        │ embedding_provider.py│
                        └─────┬───────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
              ┌─────▼─────┐      ┌─────▼──────┐
              │  local    │      │  remote    │
              │  (기본)   │      │  (API 키)  │
              └─────┬─────┘      └────────────┘
                    │
          ┌─────────┴──────────┐
          │                    │
    ┌─────▼──────┐    ┌───────▼───────┐
    │ LOCAL_     │    │ HuggingFace   │
    │ EMBEDDING_ │    │ Hub 다운로드   │
    │ MODEL_PATH │    │               │
    │ (폐쇄망)   │    │ (온라인)      │
    └────────────┘    └───────────────┘
```

**파일**: `pdftablesearch/local_embeddings.py`

```python
class SentenceTransformerEmbeddings:
    def __init__(self, model_name="BAAI/bge-m3", local_model_path=""):
        # local_model_path가 설정되면 로컬 폴더에서 직접 로드
        # 아니면 HuggingFace Hub에서 다운로드
        # HF_HUB_OFFLINE=1 환경변수로 오프라인 모드 지원

    def embed_documents(texts: List[str]) -> List[List[float]]:
        # 배치 임베딩 (batch_size=20)

    def embed_query(text: str) -> List[float]:
        # 단일 쿼리 임베딩
```

### 4.2 Weaviate 스키마

**파일**: `pdftablesearch/vectorstores/weaviate_schema.py`

두 개의 컬렉션을 사용한다:

#### PdfTables 컬렉션

```python
# 공통 속성
{
    "page_content": DataType.TEXT,       # 검색 대상 텍스트
    "doc_hash": DataType.TEXT,           # 문서 해시
    "session_id": DataType.TEXT,         # 세션 ID
    "document_name": DataType.TEXT,      # 문서명
    "table_id": DataType.TEXT,           # 표 ID
    "page_number": DataType.INT,         # 페이지 번호
    "doc_type": DataType.TEXT,           # "full_table" | "cell_chunk"
    "table_title": DataType.TEXT,        # 표 제목
    # ... 기타 메타데이터
}
# 벡터: self-provided (1024차원, bge-m3)
```

#### DocChunks 컬렉션

문서 텍스트 청크를 저장한다. 통합 검색(unified-search)에서 표와 함께 검색된다.

### 4.3 Weaviate 클라이언트

**파일**: `pdftablesearch/vectorstores/weaviate_client.py`

| 모드 | 설명 |
|------|------|
| **Embedded** | `weaviate_use_embedded=True` (기본). 앱과 함께 Weaviate 임베디드 서버 자동 시작 |
| **Remote** | 외부 Weaviate 클러스터 연결 (API 키 인증 선택) |

```python
# Embedded 모드 예시
client = weaviate.WeaviateClient(
    embedded_options=weaviate.classes.init.EmbeddedOptions(
        host="localhost",
        port=8079,
        grpc_port=50050,
        data_dir="/tmp/weaviate-data",
    )
)
```

### 4.4 WeaviateTableVectorStore

**파일**: `pdftablesearch/vectorstores/weaviate_store.py`

| 메서드 | 설명 |
|--------|------|
| `add_documents(documents, session_id)` | 문서 추가 (임베딩 자동 생성) |
| `similarity_search(query, k, filter)` | 하이브리드/벡터 유사도 검색 |
| `delete_where(filter)` | 조건부 삭제 (세션 정리) |
| `list_documents(session_id)` | 세션 내 문서 목록 |

---

## 5. 검색 아키텍처

### 5.1 검색 계층 구조

```
                    사용자 질의
                        │
          ┌─────────────┼─────────────┐
          │             │             │
    ┌─────▼─────┐ ┌────▼─────┐ ┌────▼──────────┐
    │ 표 검색   │ │스마트검색│ │ 통합 검색     │
    │ /search   │ │/smart    │ │/unified-search│
    └─────┬─────┘ └────┬─────┘ └────┬──────────┘
          │             │            │
          ▼             ▼            ▼
    Vector만       Vector +      Vector + BM25
                   LLM 선택      + RRF Fusion
```

### 5.2 하이브리드 검색 (Vector + BM25 + RRF)

**파일**: `pdftablesearch/hybrid_search.py`

두 개의 독립적인 검색 결과를 **Reciprocal Rank Fusion (RRF)** 로 융합한다.

```python
# RRF 공식
_RRF_K = 60  # 연구에서 도출된 상수
score = Σ (1 / (k + rank))  # 각 검색 결과의 순위 기반 점수 합산
```

| 검색 방식 | 특징 | 강점 |
|-----------|------|------|
| **Vector Search** | 의미적 유사도 | "자산 규모" ↔ "총자산" 매칭 |
| **BM25 Search** | 키워드 매칭 | 정확한 숫자, 고유명사 매칭 |
| **RRF Fusion** | 순위 기반 융합 | 두 방식의 장점 결합 |

BM25 검색 시 제목(title)에 **2배 가중치**를 적용한다:
```python
score = len(query_tokens & content_tokens) + len(query_tokens & title_tokens) * 2
```

### 5.3 스마트 검색 (LLM 표 선택)

**파일**: `pdftablesearch/smart_search.py`

2단계 검색으로 정확도를 높인다:

```
Phase 1: Vector 검색으로 top-20 후보 추출
              │
Phase 2: LLM이 후보 중 가장 관련성 높은 표 1개 선택
              │
         ┌────┴────┐
         │ 결과    │
         │ - best  │ (LLM 선택)
         │ - alt 2 │ (Vector top-2)
         └─────────┘
```

### 5.4 통합 검색 (Unified Search)

**파일**: `pdftablesearch/web_server.py` (`/api/unified-search`)

표와 텍스트를 동시에 검색하여 LLM이 종합 답변을 생성한다.

```
Phase 1: 표 Vector 검색 (k=15)
Phase 2: 텍스트 Vector + BM25 → RRF Fusion (k=8)
Phase 3: 출처(Source) 필터링 + 중복 제거
Phase 4: LLM 답변 생성 (출처 인용 포함, SSE 스트리밍)
```

LLM 프롬프트에서 **환각 방지** 규칙을 적용:
- 출처에 없는 내용은 답변하지 않음
- 숫자 데이터는 원문 그대로 인용
- 불확실한 경우 "제공된 문서에서 해당 정보를 찾을 수 없습니다"로 응답

---

## 6. RAG 파이프라인

### 6.1 문서 청킹 (`doc_processing.py`)

```
HTML → 텍스트 블록 추출 → 문단 분할 → 긴 텍스트 분할
                                    │
                              ┌─────┴─────┐
                              │ 분할 기준 │
                              │ - 。 . \n  │
                              │ - 최소 크기│
                              │ - 최대 크기│
                              └───────────┘
```

청크 메타데이터:
```python
{
    "page_number": int,
    "paragraph_index": int,
    "document_name": str,
    "chunk_type": "text",
}
```

### 6.2 표 Q&A (`table_qa.py`)

```
사용자 질문
    │
    ▼
smart_search() → 관련 표 검색
    │
    ▼
표 HTML + 제목 → LLM 프롬프트 구성
    │
    ▼
LLM 답변 생성 (SSE 스트리밍)
```

### 6.3 문서 Q&A (`ask-document`)

```
사용자 질문
    │
    ▼
Vector + BM25 → RRF Fusion (표 + 텍스트)
    │
    ▼
컨텍스트 빌드 (출처 포함)
    │
    ▼
LLM 답변 생성 (출처 인용, SSE 스트리밍)
    │
    ▼
출처 클릭 → PDF 페이지 렌더링 + 하이라이트
```

### 6.4 리랭킹 (`reranker.py`)

| 방식 | 설명 |
|------|------|
| `ZaiRerankCompressor` | LLM API 기반 리랭킹 |
| `CrossEncoderReranker` | 로컬 CPU 모델 (msmarco-MiniLM-L-6-v2) |

---

## 7. 인증 (LDAP + JWT)

### 7.1 인증 흐름

```
┌──────────┐    POST /api/auth/login    ┌──────────┐
│  Browser │ ◄───────────────────────► │  FastAPI  │
│          │    {username, password}    │           │
│          │                            │     ┌────┴────┐
│          │                            │     │  LDAP   │
│          │                            │     │ 서버    │
│          │    Set-Cookie: auth_token  │     │ :3890   │
│          │ ◄──────────────────────── │     └─────────┘
│          │    (httpOnly, JWT)         │
└──────────┘                            └──────────┘
     │
     │ 이후 모든 요청에 쿠키 자동 포함
     ▼
┌──────────┐    모든 API 요청           ┌──────────┐
│  Browser │ ────────────────────────► │  FastAPI  │
│          │    Cookie: auth_token=xxx │  (검증)   │
└──────────┘                            └──────────┘
```

### 7.2 LDAP 인증 (`auth.py`)

Service Account Bind 방식으로 인증한다:

```python
# 1. 서비스 계정으로 LDAP 바인드
conn.bind(ldap_server_url, bind_dn, bind_password)

# 2. 사용자 검색
conn.search(base_dn, f"(uid={username})")

# 3. 사용자 DN으로 비밀번호 검증
conn.bind(user_dn, password)
```

### 7.3 JWT 토큰

```python
# 토큰 발급
payload = {
    "sub": user_id,
    "name": user_name,
    "roles": user_roles,
    "exp": datetime.utcnow() + timedelta(hours=8),
}
token = jwt.encode(payload, AUTH_SECRET_KEY, algorithm="HS256")

# 쿠키 설정
response.set_cookie(
    key="auth_token",
    value=token,
    httponly=True,
    secure=AUTH_COOKIE_SECURE,
    samesite="lax",
)
```

### 7.4 권한 모델

| 역할 | 권한 |
|------|------|
| `user` | 세션 생성, PDF 업로드, 검색, Q&A |
| `admin` | 모든 권한 + 관리 기능 |

세션은 생성 시 `owner_id`를 기록하며, 인증된 사용자는 자신의 세션만 접근할 수 있다.

---

## 8. PII 마스킹

### 8.1 감지 대상

**파일**: `pdftablesearch/pii_masking.py`

| 유형 | 정규식 | 예시 | 마스킹 결과 |
|------|--------|------|-------------|
| 주민등록번호 | `\d{6}-[1-4]\d{6}` | 900101-1234567 | 90****56 |
| 외국인등록번호 | `\d{6}-[5-8]\d{6}` | 900101-5123456 | 90****56 |
| 운전면허번호 | `\d{3}-\d{2}-\d{5}` | 12-34-567890 | 12****90 |
| 신용카드번호 | `\d{4}-\d{4}-\d{4}-\d{4}` | 1234-5678-9012-3456 | 12****56 |
| 휴대전화번호 | `01[016789]-\d{3,4}-\d{4}` | 010-1234-5678 | 010***78 |
| 유선전화번호 | `02\|0[3-6][1-5]-\d{3,4}-\d{4}` | 02-123-4567 | 02-***67 |
| 이메일 | `[\w.+-]+@[\w.-]+\.\w{2,}` | user@company.com | u***r@c***y.com |
| 여권번호 | `[A-Z]{1,2}\d{7,8}` | AB1234567 | AB***67 |
| 차대번호 | `[A-HJ-NPR-Z0-9]{17}` | KMHJN81BPFU123456 | KM****56 |

### 8.2 마스킹 전략

```python
def _mask_digits(value, left_digits, right_digits):
    """숫자만 기준으로 앞/뒤 일부를 남기고 형식 유지"""
    # 900101-1234567 → 90****56 (앞 2자리, 뒤 2자리 보존)

def _mask_keep_edges(value, left, right):
    """문자열 양 끝 일부만 남기고 중간을 마스킹"""
    # AB1234567 → AB***67 (앞 2, 뒤 2 보존)

def _mask_email(value):
    """이메일은 로컬/도메인 각각 축약 마스킹"""
    # user@company.com → u***r@c***y.com
```

### 8.3 마스킹 적용 지점

| 지점 | 함수 | 대상 |
|------|------|------|
| 표 직렬화 | `mask_pii_text()` | table_title, table_html |
| 표 HTML | `mask_pii_in_html()` | HTML 텍스트 노드만 |
| 문서 텍스트 | `mask_pii_text()` | documents/text, documents/markdown |
| 검색 결과 | `mask_pii_text()` + `mask_pii_in_html()` | 모든 검색 결과 |
| 이미지 문맥 | `mask_pii_text()` | 이미지 주변 텍스트 |
| RAG 컨텍스트 | `mask_pii_text()` | LLM 프롬프트에 들어가는 출처 텍스트 |
| 출처 PDF | `mask_pii_text()` | 문서 보기 하이라이트 텍스트 |

### 8.4 스프레드시트 컨텍스트 인식

숫자만 있는 셀(예: `900101`)은 PII가 아닐 수 있다. 주변 셀의 라벨(예: "주민등록번호")이 PII 키워드와 일치할 때만 마스킹한다.

```python
# 컨텍스트 키워드 예시
"resident_registration_number": {"주민등록번호", "주민번호", "rrn", ...}
"credit_card_number": {"신용카드번호", "카드번호", "cardnumber", ...}
```

---

## 9. 세션 관리

### 9.1 세션 구조

```python
_sessions: Dict[str, dict] = {
    "session_uuid": {
        "name": "세션 이름",
        "owner_id": "user_id",          # 인증된 사용자
        "created_at": datetime,
        "last_activity": datetime,
        "search_count": 0,
        "qa_count": 0,
        "upload_dir": "/tmp/.../uploads",   # 업로드된 PDF
        "data_dir": "/tmp/.../data",        # Weaviate 데이터
        "doc_chunks_dir": "/tmp/.../chunks", # 문서 청크
        "pdfs": {
            "busan.pdf": {
                "tables": [...],         # 추출된 표
                "page_count": 22,
                "table_count": 24,
                "bm25_index": BM25Okapi, # 키워드 검색 인덱스
                "bm25_corpus": [...],    # BM25 코퍼스
            }
        },
        "vector_store": WeaviateTableVectorStore,
        "embeddings": SentenceTransformerEmbeddings,
    }
}
```

### 9.2 세션 수명 주기

```
생성 (POST /api/sessions)
   │
   ├── PDF 업로드 (POST /api/upload)
   │      ├── 파싱 + 표 추출 + 벡터화
   │      └── 다중페이지 표 감지 → 팝업
   │
   ├── 검색 (POST /api/search, /api/unified-search)
   │
   ├── Q&A (POST /api/qa, /api/ask-document)
   │
   └── 삭제 (DELETE /api/sessions/{id})
          ├── upload_dir 삭제
          ├── data_dir 삭제
          └── Weaviate 컬렉션 데이터 삭제
```

> **주의**: 세션은 인메모리(`_sessions` dict)에 저장된다. 서버 `--reload` 재시작 시 모든 세션이 손실되며 PDF 재업로드가 필요하다.

### 9.3 세션 Idle Timeout

**파일**: `pdftablesearch/auth.py`, `web/src/components/SessionTimeoutGuard.tsx`

```
auth.py:
  _session_activity: dict[str, float]  # session_id → 마지막 활동 timestamp
  idle_timeout: 600초 (10분, config.auth_idle_timeout_seconds)
  warn_before: 60초 (만료 1분 전 경고, config.auth_warn_before_seconds)
  session_ttl: 3600초 (1시간 절대 만료, config.auth_session_ttl_seconds)

_touch_session(session_id): 매 요청마다 활동 시간 갱신
_is_session_active(session_id): idle_timeout 기준으로 유효성 검증
_end_session(session_id): 세션 만료 처리

프론트엔드 SessionTimeoutGuard:
  - 우측 하단 타이머 (mm:ss 형식)
  - mousemove/click/keydown/scroll/touchstart 감지 → 매 30초마다 POST /api/auth/touch
  - 만료 1분 전 경고 모달 → "확인" 시 touch 갱신
  - 만료 시 자동 로그아웃 + 재로그인 유도
```

### 9.4 서비스 이용 동의 (AgreementOverlay)

**파일**: `web/src/components/AgreementOverlay.tsx`

- 로그인 후 최초 1회 모달 팝업으로 서비스 이용 동의 수락
- `sessionStorage`에 동의 상태 저장 (탭 간 공유 불가, 세션 단위)
- "확인" 시 닫고 메인 화면 진입

### 9.5 기업금융심사 테이블 필터

**파일**: `web/src/components/CreditReviewView.tsx`, `web/src/components/DocumentViewer.tsx`

```typescript
// DocumentViewer.tsx
export type TableFilterMode = 'all' | 'outer' | 'inner' | 'inner-or-standalone';

const currentPageTables = overlays.filter(o => o.page === currentPage).filter(o => {
    if (tableFilter === 'outer') return !o.is_inner;
    if (tableFilter === 'inner') return o.is_inner;
    if (tableFilter === 'inner-or-standalone') return o.is_inner || !o.has_inner_tables;
    return true;  // 'all'
});

// CreditReviewView.tsx
<DocumentViewer tableFilter="inner-or-standalone" />
```

필터 동작:
- `inner-or-standalone`: 이중표(outer with inner) → inner 테이블만, 일반표(outer without inner) → outer 표시
- `inner`: inner 테이블만 표시
- `outer`: outer 테이블만 표시
- `all`: 모든 테이블 표시

---

## 10. API 레퍼런스

### 인증

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/auth/login` | LDAP 로그인 → JWT httpOnly 쿠키 발급 |
| `POST` | `/api/auth/logout` | 쿠키 삭제 |
| `GET` | `/api/auth/me` | 현재 사용자 정보 |
| `GET` | `/api/auth/config` | 세션 타임아웃 설정 (idle_timeout, warn_before, session_ttl) |
| `POST` | `/api/auth/touch` | 세션 활동 시간 갱신 (idle timeout 리셋) |

### 세션

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/sessions` | 세션 목록 |
| `POST` | `/api/sessions` | 세션 생성 |
| `GET` | `/api/sessions/{id}` | 세션 상세 |
| `PUT` | `/api/sessions/{id}` | 세션 이름 수정 |
| `DELETE` | `/api/sessions/{id}` | 세션 삭제 (데이터 정리) |

### 문서

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/upload` | PDF 업로드 → 파싱 → 표 추출 → 벡터화 → 다중페이지 감지 |
| `GET` | `/api/pdfs` | 세션 내 PDF 목록 |
| `DELETE` | `/api/pdfs/{name}` | 특정 PDF 삭제 |
| `GET` | `/api/documents/pdf` | 원본 PDF 다운로드 |
| `GET` | `/api/documents/page-image` | PDF 페이지 PNG 렌더링 |
| `GET` | `/api/documents/text` | 텍스트 추출 (PII 마스킹) |
| `GET` | `/api/documents/tables` | 표 목록 (PII 마스킹) |
| `GET` | `/api/documents/html` | 표 HTML (PII 마스킹) |
| `GET` | `/api/documents/images` | 이미지 + 문맥 추출 |

### 검색

| Method | Path | 설명 | 응답 |
|--------|------|------|------|
| `POST` | `/api/search` | 벡터 유사도 검색 | JSON |
| `POST` | `/api/smart-search` | AI 표 선택 검색 | **SSE** |
| `POST` | `/api/unified-search` | 통합 문서 검색 (표+텍스트) | **SSE** |
| `POST` | `/api/unified-followup` | 후속 질문 | **SSE** |

### AI

| Method | Path | 설명 | 응답 |
|--------|------|------|------|
| `POST` | `/api/qa` | 표 Q&A | **SSE** |
| `POST` | `/api/ask-document` | 문서 Q&A (RRF Fusion) | **SSE** |
| `POST` | `/api/table-calculate` | 표 계산 (LLM) | **SSE** |

### 표 관리

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/confirm-table-groups` | 다중페이지 표 그룹 확인 |
| `POST` | `/api/table-transpose/{id}` | 표 전치 |

### 번역

| Method | Path | 설명 | 응답 |
|--------|------|------|------|
| `POST` | `/api/translate-html` | 페이지별 HTML 번역 | **SSE** |
| `POST` | `/api/translate` | 문서 텍스트 번역 | **SSE** |

### SSE 이벤트 형식

```
event: progress
data: {"phase": "vector_search", "message": "벡터 검색 중..."}

event: token
data: {"token": "답변 토큰"}

event: result
data: {"table_id": "...", "relevance_score": 0.95, ...}

event: done
data: {"time_seconds": 3.2}

event: error
data: {"error": "오류 메시지"}
```

---

## 11. 프론트엔드 아키텍처

### 11.1 상태 관리 (Zustand)

**파일**: `web/src/store/useAppStore.ts`

```
┌──────────────────────────────────────────────┐
│              useAppStore                      │
├──────────────────────────────────────────────┤
│ sessionId / sessionName                      │
│ pdfs: PdfInfo[]                              │
│ totalTables / totalPages                     │
│ results: TableResult[]   (검색 결과)         │
│ smartResult             (스마트 검색)        │
│ qaMessages: QAMessage[] (QA 대화)            │
│ selectedPdfs: string[]   (검색 대상 필터)    │
│ highlightRegion          (PDF 하이라이트)     │
│ overlayVersion           (표 오버레이 버전)   │
├──────────────────────────────────────────────┤
│ localStorage 자동 저장                       │
│ - pdfts_{sid}_search: 검색 결과             │
│ - pdfts_{sid}_qa: QA 대화                   │
│ - pdfts_{sid}_tableqas: 표 QA               │
└──────────────────────────────────────────────┘
```

### 11.2 핵심 컴포넌트

| 컴포넌트 | 역할 |
|----------|------|
| `App.tsx` | 루트 레이아웃, 업로드/검색 핸들러, authConfig 통합 |
| `Sidebar.tsx` | PDF 업로드, 목록, 세션 관리, 병합 팝업 |
| `TabBar.tsx` | 탭 네비게이션 |
| `SearchBar.tsx` | 검색어 입력 + PDF 필터 |
| `SearchResults.tsx` | 검색 결과 표시 |
| `TableCard.tsx` | 표 카드 (iframe 렌더링, Q&A, 다운로드) |
| `QAPanel.tsx` | 문서 QA 채팅 |
| `ChatBubble.tsx` | 메시지 + 출처 팝업 → PDF 하이라이트 |
| `DocumentViewer.tsx` | PDF 렌더링 (pdf.js) + 표 오버레이 + inner-or-standalone 필터 |
| `CreditReviewView.tsx` | 기업금융심사 (이미지 분석, inner-or-standalone 모드) |
| `TableGroupSuggestionPopup.tsx` | 다중페이지 표 병합 팝업 |
| `SessionTimeoutGuard.tsx` | 세션 idle timeout 타이머 + 만료 경고 모달 |
| `AgreementOverlay.tsx` | 로그인 후 서비스 이용 동의 팝업 |

### 11.3 PDF 렌더링 & 하이라이트

```
DocumentViewer.tsx
    │
    ├── pdf.js (CDN, v4.0.379)
    │      └── canvas에 PDF 페이지 렌더링
    │
    ├── 표 오버레이
    │      └── bounding_box → viewport.convertToViewportPoint()
    │         → 반투명 영역 + 클릭 시 팝업
    │
    └── 하이라이트 (highlightRegion)
           └── 6단계 폴백 매칭
               1. Full match
               2. Prefix match
               3. Phrase match
               4. Sliding window
               5. Raw text
               6. Character overlap
```

### 11.4 표 HTML 렌더링

XSS 방지를 위해 샌드박스 iframe을 사용한다:

```tsx
<iframe
  sandbox="allow-same-origin"
  srcDoc={sanitizedTableHtml}
/>
```

---

## 12. 폐쇄망 배포

### 12.1 구성 요소

| 구성 요소 | 크기 | 반입 방식 |
|-----------|------|----------|
| Python 패키지 | ~200MB | `uv pip export` → `.whl` + `.tar.gz` |
| bge-m3 모델 | 2.1GB | `model.save()` → 500MB × 5 분할 tar |
| Weaviate 바이너리 | 240MB | 단일 tar 아카이브 |
| Node.js 패키지 | ~100MB | `npm pack` 또는 사전 빌드 |
| 소스 코드 | ~5MB | git archive 또는 tar |

### 12.2 로컬 임베딩 설정

```bash
# .env
LOCAL_EMBEDDING_MODEL_PATH=/opt/models/bge-m3-local
HF_HUB_OFFLINE=1
```

모델 로딩 흐름:
```
config.local_embedding_model_path 설정됨?
    │
    ├── YES → 로컬 폴더에서 직접 로드
    │         SentenceTransformer("/opt/models/bge-m3-local")
    │
    └── NO  → HuggingFace Hub에서 다운로드
              SentenceTransformer("BAAI/bge-m3")
```

### 12.3 분할 압축/해제

```bash
# 압축 (500MB 분할)
tar cf - bge-m3-local/ | split -b 500m - bge-m3-local.tar.part_

# 해제
cat bge-m3-local.tar.part_* | tar xf -
```

> 사내 반입 시스템은 `.tar` 확장자만 허용하므로 `part_aa → .tar.001` 등으로 이름 변경 필요.

---

## 13. 환경 변수 전체 목록

### LLM

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ZAI_LLM_ENDPOINT` | `https://ollama.com/v1` | Ollama API 엔드포인트 |
| `ZAI_LLM_MODEL` | `gpt-oss:120b` | LLM 모델명 |
| `ZAI_LLM_RERANK_MODEL` | `gpt-oss:120b` | 리랭킹 모델명 |
| `ZAI_API_KEY` | (없음) | z.ai API 키 (리모트 임베딩용) |
| `OLLAMA_API_KEY` | (없음) | Ollama API 키 |

### 임베딩

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LOCAL_EMBEDDING_MODEL` | `BAAI/bge-m3` | 임베딩 모델명 |
| `LOCAL_EMBEDDING_MODEL_PATH` | (빈 문자열) | 로컬 모델 경로 (폐쇄망) |
| `EMBEDDING_DEVICE` | `cpu` | 임베딩 디바이스 |

### 처리 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MAX_FILE_SIZE_MB` | `100` | 최대 파일 크기 (MB) |
| `API_TIMEOUT_SECONDS` | `30` | API 타임아웃 |
| `API_MAX_RETRIES` | `3` | 최대 재시도 횟수 |
| `EMBEDDING_BATCH_SIZE` | `20` | 임베딩 배치 크기 |
| `PARALLEL_WORKERS` | `4` | 병렬 처리 워커 수 |

### 검색

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SMART_SEARCH_TOP_K` | `20` | 스마트 검색 후보 수 |
| `RERANKER_TOP_K` | `10` | 리랭킹 결과 수 |
| `CONTENT_MAX_LENGTH` | `500` | LLM 입력 최대 길이 |

### LDAP 인증

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LDAP_SERVER_URL` | (빈 문자열) | LDAP 서버 URL |
| `LDAP_BASE_DN` | (빈 문자열) | 검색 Base DN |
| `LDAP_SERVICE_BIND_DN` | (빈 문자열) | 서비스 계정 DN |
| `LDAP_SERVICE_BIND_PASSWORD` | (빈 문자열) | 서비스 계정 비밀번호 |
| `LDAP_USER_FILTER` | `(uid={username})` | 사용자 검색 필터 |
| `LDAP_ATTR_NAME` | `cn` | 이름 속성 |
| `LDAP_ATTR_EMAIL` | `mail` | 이메일 속성 |
| `LDAP_ATTR_DEPARTMENT` | `departmentNumber` | 부서 속성 |
| `LDAP_ATTR_ROLE` | `title` | 역할 속성 |
| `LDAP_USE_TLS` | `false` | TLS 사용 여부 |

### JWT

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AUTH_SECRET_KEY` | `dev-secret-change-me` | JWT 서명 키 |
| `AUTH_TOKEN_EXPIRE_HOURS` | `8` | 토큰 만료 시간 |
| `AUTH_COOKIE_NAME` | `auth_token` | 쿠키 이름 |
| `AUTH_COOKIE_SECURE` | `false` | HTTPS 전용 |
| `AUTH_COOKIE_SAMESITE` | `lax` | SameSite 정책 |

### Weaviate

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `WEAVIATE_HOST` | `localhost` | Weaviate 호스트 |
| `WEAVIATE_PORT` | `8079` | HTTP 포트 |
| `WEAVIATE_GRPC_PORT` | `50050` | gRPC 포트 |
| `WEAVIATE_USE_EMBEDDED` | `true` | Embedded 모드 |
| `WEAVIATE_DATA_DIR` | `/tmp/weaviate-data` | 데이터 디렉토리 |
| `WEAVIATE_TABLE_COLLECTION` | `PdfTables` | 표 컬렉션명 |
| `WEAVIATE_CHUNK_COLLECTION` | `DocChunks` | 청크 컬렉션명 |
| `WEAVIATE_HYBRID_ALPHA` | `0.5` | 하이브리드 검색 알파 |
| `WEAVIATE_SEARCH_MODE` | `vector` | 기본 검색 모드 |
| `VECTOR_BACKEND` | `weaviate` | 벡터 DB 백엔드 |

### 기타

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `APP_ENV` | `dev` | 실행 환경 |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,...` | CORS 허용 출처 |
| `LOG_LEVEL` | `INFO` | 로깅 레벨 |
| `CACHE_ENABLED` | `true` | LLM 캐시 활성화 |
| `CACHE_DIR` | `./.cache` | 캐시 디렉토리 |
| `LLM_CACHE_TTL_SECONDS` | `86400` | 캐시 TTL (24시간) |

---

## 프로젝트 구조

```
pdftablesearch/
├── pdftablesearch/                  # Python 백엔드
│   ├── web_server.py                # FastAPI 서버 (~2400줄)
│   ├── auth.py                      # LDAP + JWT 인증
│   ├── config.py                    # 환경설정 (pydantic-settings)
│   ├── core.py                      # 검색 오케스트레이션
│   ├── search.py                    # PDFTableSearch 클래스
│   ├── smart_search.py              # LLM 표 선택 검색
│   ├── hybrid_search.py             # Vector + BM25 + RRF Fusion
│   ├── table_utils.py               # 표 감지/매칭/병합 (~710줄)
│   ├── table_qa.py                  # 표 Q&A
│   ├── doc_processing.py            # 문서 분할
│   ├── llm_client.py                # LLM 클라이언트
│   ├── pii_masking.py               # 개인정보 마스킹
│   ├── reranker.py                  # 리랭킹
│   ├── translation.py               # 번역
│   ├── local_embeddings.py          # 로컬 임베딩 (bge-m3)
│   ├── embedding_provider.py        # 임베딩 팩토리
│   ├── table_structure_extractor.py # 표 계층 구조 추출
│   ├── ldap_server.py               # 로컬 OpenLDAP 래퍼
│   ├── vectorstores/                # Weaviate
│   │   ├── __init__.py              # 팩토리
│   │   ├── weaviate_client.py       # 연결 관리
│   │   ├── weaviate_store.py        # CRUD + 검색
│   │   ├── weaviate_schema.py       # 스키마 정의
│   │   └── weaviate_server.py       # Embedded 서버
│   └── loader/                      # PDF 파싱
│       ├── __init__.py              # PDFProcessor (파이프라인)
│       ├── html_parser.py           # HTML 표 추출
│       ├── json_parser.py           # JSON 메타데이터 파싱
│       ├── markdown_parser.py       # Markdown 제목/문맥
│       └── matcher.py               # Jaccard 매칭
│
├── web/                             # React 프론트엔드
│   └── src/
│       ├── api/client.ts            # API 클라이언트 (SSE)
│       ├── store/useAppStore.ts     # Zustand 상태관리
│       ├── types/index.ts           # TypeScript 타입
│       └── components/
│           ├── App.tsx              # 루트 컴포넌트
│           ├── LoginView.tsx        # LDAP 로그인
│           ├── Sidebar.tsx          # 사이드바
│           ├── SearchBar.tsx        # 검색 바
│           ├── SearchResults.tsx    # 검색 결과
│           ├── TableCard.tsx        # 표 카드
│           ├── QAPanel.tsx          # 문서 QA
│           ├── ChatBubble.tsx       # 메시지 + 출처
│           ├── DocumentViewer.tsx   # PDF 뷰어
│           ├── CreditReviewView.tsx # 기업금융심사
│           ├── TableGroupSuggestionPopup.tsx # 병합 팝업
│           └── ...
│
├── scripts/ldap/                    # LDAP 서버 스크립트
├── docs/                            # 문서
├── pyproject.toml                   # Python 패키지 설정
└── .env                             # 환경변수
```
