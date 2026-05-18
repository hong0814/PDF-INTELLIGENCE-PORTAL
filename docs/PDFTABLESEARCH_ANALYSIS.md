# PDFTableSearch 프로젝트 분석 보고서

## 📋 개요

**PDFTableSearch**는 한국어 PDF 문서의 표를 자연어 질문으로 의미적 검색할 수 있는 Python 3.11+ 라이브러리입니다. LangChain, ChromaDB, SentenceTransformers, z.ai API를 통합하여 **하이브리드 검색 시스템**을 구현했습니다.

---

## 🏗️ 아키텍처 핵심 컴포넌트

### 1. PDFProcessor (`loader.py` - 912줄)

**역할**: PDF 문서 로드 및 테이블 추출 엔진

**주요 기능**:
- **PDF 변환**: opendataloader-pdf 사용 (hybrid 모드 지원)
  - HTML + JSON 출력 생성
  - 하이브리드 모드: `docling-fast` (http://localhost:5002)

- **HTML 우선 테이블 추출**:
  - BeautifulSoup로 모든 `<table>` 요소 추출
  - 이전 형제 태그(h1-h6)에서 제목 추출
  - colspan/rowspan 병합 셀 완벽 지원

- **내용 기반 메타데이터 매칭**:
  - HTML 테이블과 JSON 메타데이터 간 실제 내용 유사도 계산
  - 단순 인덱스 매칭 대신 텍스트 포함/단어 중복(Jaccard) 기반 매칭
  - 페이지 번호, 바운딩 박스 좌표 정확하게 매핑

- **안전한 HTML 렌더링**:
  - `<script>` 태그 제거
  - 이벤트 핸들러 속성 제거 (`onclick`, `onload` 등)
  - `javascript:` URL 제거
  - XSS 방지

**주요 메서드**:
```python
convert_pdf(pdf_path, use_hybrid=True)  # PDF → HTML+JSON 변환
load_documents(pdf_path)              # 문서 로드 + 테이블 추출
get_documents()                       # 추출된 LangChain Documents 반환
```

---

### 2. PDFTableSearch (`search.py` - 478줄)

**역할**: 효율적인 테이블 검색 클래스

**주요 특징**:
- **3단계 캐싱 전략**:
  1. **모델 캐싱**: 임베딩 모델 한 번 로드 후 재사용
  2. **문서 캐싱**: 로드된 PDF 문서를 메모리에 저장
  3. **벡터 저장소 공유**: 여러 검색 간 ChromaDB 인덱스 재사용

**주요 메서드**:
```python
__init__(model_name, chroma_persist_dir, device)
search(pdf_path, query, max_results, use_llm_rerank, use_hybrid, reset_vector_store)
search_many(pdf_paths, query, max_total_results, max_results_per_doc)
smart_search(pdf_path, query, top_k, llm_model, fallback_to_vector)
get_vector_store_stats()          # 벡터 저장소 통계
list_stored_tables()             # 저장된 모든 테이블 목록
inspect_vector_store()            # 상세 정보 출력
clear_cache()                     # 문서 캐시 초기화
reset_vector_store()              # 벡터 저장소 리셋
```

---

### 3. TableVectorStore (`vectorstore.py` - 306줄)

**역할**: ChromaDB 벡터 저장소 관리 래퍼

**주요 기능**:
- **지연 초기화**: 첫 호출 시에만 ChromaDB 인스턴스 생성
- **영구 저장**: 디스크에 벡터 인덱스 저장 (`./.chroma/`)
- **메타데이터 필터링**: 문서별 검색 지원 (`filter_metadata`)
- **CRUD 및 통계**: 문서 추가, 검색, 삭제, 통계 제공

**주요 메서드**:
```python
add_documents(documents)           # 문서 추가 (또는 기존에 추가)
similarity_search(query, k, filter_metadata)  # 코사인 유사도 검색
get_document_count()                # 문서 수 반환
get_stats()                       # 통계 정보 반환
reset()                           # 벡터 저장소 완전 삭제
```

---

### 4. ZaiLLMClient (`llm_client.py` - 398줄)

**역할**: z.ai GLM-5.1 API를 통한 테이블 선택

**프롬프트 구조**:
```python
# 시스템 프롬프트
"당신은 금융 테이블 검색 전문가입니다.
HTML 테이블 구조(colspan, rowspan, th, td)를 분석하고,
사용자 검색어에 가장 적합한 테이블을 선택하세요."

# 사용자 프롬프트
"사용자 쿼리: {query}

사용 가능한 테이블:
{table_descriptions}

다음 형식의 JSON 객체로만 응답하세요:
{
  "selected_index": <1-based index>,
  "confidence": <0.0 to 1.0>,
  "reasoning": "<선택 사유 (한국어)>"
}"
```

**응답 모델**:
```python
@dataclass
class LLMSelectionResult:
    selected_index: int       # 1-based 인덱스
    confidence: float        # 0.0~1.0 신뢰도 점수
    reasoning: str           # 선택 사유 (한국어)
    raw_response: str       # 원본 응답 (디버깅용)
```

**안전한 HTML 트리케이션**:
- 500자 안전 트리케이션
- 열리는 `<` 태그에서 컷, `>` 이전에서 백업
- 마크다운 블록 제거
- 정규표현을 통한 JSON 객체 추출

---

### 5. Smart Search (`smart_search.py` - 353줄)

**역할**: 벡터 검색 + LLM 선택 결합

**파이프라인**:
```
Phase 1: 벡터 검색 (top_k=20 후보 추출)
    ↓
Phase 2: LLM 테이블 선택 (가장 적합한 1개)
    ↓
Phase 3: 결과 반환 (LLM 실패 시 벡터 #1 폴백)
```

**주요 설정**:
- `_DEFAULT_TOP_K = 20`: LLM 평가 후보 수
- `_DEFAULT_LLM_MODEL = "glm-5.1"`: 사용 LLM 모델
- `_DEFAULT_CONTENT_MAX_LENGTH = 500`: 후보당 최대 내용 길이

---

### 6. 임베딩 시스템

두 가지 임베딩 옵션 제공:

#### **ZaiEmbeddings** (`embeddings.py`)
- **원격 API**: z.ai API 호출
- **장점**: 최신 모델, API 키 필요
- **용도**: LangChain 호환 임베딩

#### **SentenceTransformerEmbeddings** (`local_embeddings.py` - 107줄)
- **로컬 실행**: SentenceTransformers 모델 사용
- **기본 모델**: `BAAI/bge-m3` (한국어 지원, 100+ 언어)
- **장점**: API 키 불필요, 오프라인 가능
- **대안 모델**:
  - `distiluse-base-multilingual-cased-v2` (가볍고 빠름)
  - `paraphrase-multilingual-MiniLM-L12-v2` (한국어 최적화)

---

### 7. 데이터 모델 (`models.py` - 270줄)

```python
@dataclass
class TableSearchResult:
    page_number: int
    bounding_box: List[int]        # [x1, y1, x2, y2]
    table_html: str               # HTML 형식 (colspan/rowspan 포함)
    table_markdown: str           # Markdown 폴백
    table_id: str                # "table_{page}_{id}"
    document_name: str
    relevance_score: Optional[float]    # 벡터 유사도 점수
    rerank_score: Optional[float]      # LLM 재랭킹 점수
    table_title: Optional[str]

@dataclass
class MultiDocumentSearchResult:
    results: List[TableSearchResult]
    document_counts: Dict[str, int]
    total_results: int
    query: str
```

---

### 8. 예외 처리 (`exceptions.py` - 162줄)

```
TableSearchError (기본 예외)
├── PDFProcessingError           # PDF 처리 실패
├── TableParsingError           # 테이블 파싱 실패
├── MetadataMismatchError       # 메타데이터 불일치
├── VectorIndexError          # 벡터 인덱스 오류
├── VectorSearchError          # 벡터 검색 오류
├── ResultFormattingError      # 결과 포맷팅 오류
└── APIError (기본 API 예외)
    ├── APIConnectionError       # 연결 실패
    ├── APIAuthenticationError   # 인증 실패
    └── RateLimitError         # 속도 제한 초과 (retry_after 포함)
```

---

### 9. 유틸리티 (`utils.py` - 244줄)

**주요 기능**:
- **로깅**: 환경 변수 기반 로거 생성
- **환경 변수**: `get_env()`, `get_api_key()` (필수 검증)
- **파일 검증**: `validate_pdf_path()` (존재, 읽기 가능, 크기 제한)
- **경로 정제**: `sanitize_path()` (디렉토리 트래버설 방지)
- **텍스트 처리**: `truncate_text()`, `extract_table_context()`

---

## 🧪 테스트 구조

**테스트 파일**: 10개

```
tests/
├── test_loader.py          # PDFProcessor 테스트
├── test_core.py           # search_tables() 테스트
├── test_vectorstore.py    # TableVectorStore 테스트
├── test_reranker.py       # ZaiRerankCompressor 테스트 (❌ 누락)
├── test_embeddings.py     # 임베딩 모듈 테스트
├── test_utils.py         # 유틸리티 함수 테스트
├── test_exceptions.py     # 예외 발생 및 처리 테스트
├── test_models.py         # 데이터 모델 시리얼라이제이션 테스트
└── fixtures/
    └── __init__.py
```

**테스트 프레임워크**: pytest

---

## 🌐 Streamlit 웹 인터페이스

**파일**: `streamlit_app.py` (718줄)

### 주요 기능

**1. PDF 관리 (사이드바)**:
- 다중 PDF 업로드
- 처리 상태 표시 (성공/실패/테이블 수)
- 개별 PDF 삭제
- 전체 초기화
- 전체 테이블 목록 보기 (디버깅)

**2. 검색 인터페이스 (메인)**:
- 자연어 검색어 입력
- 최대 결과 수 슬라이더 (1-20)
- Smart Search 체크박스
- 모든 PDF/특정 PDF 검색 옵션
- 디버그 모드 (후보 목록, LLM 응답 표시)

**3. 결과 표시**:
- HTML 테이블 렌더링 (`unsafe_allow_html=True`)
- 관련도 점수 표시 (거리 → 유사도 변환)
- 다운로드 버튼: HTML, Markdown, CSV
- 테이블 제목, 페이지, 문서명 표시
- 테이블 코드 보기

**4. Smart Search 결과**:
- AI 선택 결과 1위 특별 강조
- 추가 추천 테이블 2-3위 표시
- LLM 선택 이유 표시

**5. 성능 모니터링**:
- 변환 시간: PDF → HTML+JSON 변환 소요 시간
- 준비 시간: 임베딩/벡터 준비 소요 시간
- 검색 시간: 유사도 검색 실행 소요 시간
- 총 시간: 전체 검색 파이프라인 소요 시간

---

## 📊 데이터 흐름

### 단일 문서 검색 파이프라인

```
사용자 쿼리
    ↓
search_tables(pdf_path, query)
    ↓
┌─────────────────────────────────────────┐
│  PDFProcessor.load_documents()       │
│  • opendataloader-pdf 변환         │
│  • HTML 테이블 추출           │
│  • JSON 메타데이터 매칭       │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  SentenceTransformerEmbeddings       │
│  • 임베딩 생성                 │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  TableVectorStore.add_documents()   │
│  • ChromaDB에 임베딩 저장       │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  similarity_search(query, k=5)    │
│  • 코사인 유사도 검색           │
└─────────────────────────────────────────┘
    ↓
TableSearchResult[]
```

### Smart Search 파이프라인

```
사용자 쿼리
    ↓
smart_search(pdf_path, query, top_k=20)
    ↓
┌─────────────────────────────────────────┐
│  Phase 1: 벡터 검색           │
│  • PDFProcessor.load_documents()   │
│  • SentenceTransformerEmbeddings   │
│  • TableVectorStore.similarity_search() (k=20) │
└─────────────────────────────────────────┘
    ↓ (top_k=20 후보)
┌─────────────────────────────────────────┐
│  Phase 2: LLM 선택             │
│  • ZaiLLMClient.select_table()  │
│  • 후보 포맷팅 (HTML+제목)  │
│  • z.ai GLM-5.1 API 호출         │
│  • JSON 응답 파싱             │
└─────────────────────────────────────────┘
    ↓
TableSearchResult (rerank_score 포함)
```

---

## 🔗 모듈 간 의존성

```
                    ┌─────────────────────────────────────────┐
                    │        __init__.py              │
                    │   exports: search_tables, PDFTableSearch │
                    └───────────┬─────────────────────┘
                                │
               ┌────────────────┴────────────────┐
               ▼                             ▼
    ┌──────────────┐              ┌──────────────┐
    │   core.py   │◄────────────►│  search.py    │
    │ (main API)  │              │ (caching)    │
    └──────┬───────┘              └───────┬──────┘
           │                              │
           ▼                              ▼
    ┌──────────────┐              ┌──────────────┐
    │  loader.py  │◄────────────►│ vectorstore.py│
    │ (PDF 처리)  │              │ (ChromaDB)  │
    └──────┬───────┘              └───────┬──────┘
           │                              │
           ▼                              ▼
    ┌──────────────┐                  │
    │ utils.py    │◄─────────────────┘
    │ (helpers)   │
    └──────┬───────┘
           │
    ┌──────┴─────────────────────────┐
    ▼                             ▼
┌──────────────┐      ┌──────────────┐
│embeddings.py │      │smart_search.py│
│ (z.ai 임베딩)│      │ (hybrid)      │
└──────────────┘      └───────┬──────┘
                          │
                          ▼
               ┌─────────────────────────────────┐
               │  llm_client.py               │
               │  (z.ai LLM API)             │
               └─────────────────────────────────┘
                          │
                          ▼
               ┌─────────────────────────────────┐
               │  local_embeddings.py          │
               │  (SentenceTransformers)        │
               └─────────────────────────────────┘
```

---

## 🔐 의존성

### 핵심 라이브러리

```python
# PDF 처리
opendataloader-pdf[hybrid]>=2.2.1    # PDF → HTML+JSON 변환
beautifulsoup4                        # HTML 파싱

# 벡터 저장소
chromadb>=0.4.0                       # 벡터 데이터베이스

# 임베딩
sentence-transformers>=2.0.0            # 로컬 임베딩

# LangChain
langchain>=0.1.0                      # LLM 프레임워크
langchain-community>=0.0.20
langchain-core>=0.1.0
langchain-openai>=0.0.5

# LLM API
requests>=2.31.0                      # HTTP 요청

# 유틸리티
python-dotenv>=1.0.0                   # 환경 변수 로드
tenacity>=8.2.0                        # 재시도 로직
tqdm>=4.66.0                           # 진행 표시줄

# 데이터 검증
pydantic>=2.5.0                      # 데이터 모델
```

---

## 🎯 핵심 설계 패턴

### 1. **HTML 우선 접근**
- **이유**: Markdown 기반 접근은 colspan/rowspan을 손실하게 처리
- **구현**:
  - opendataloader-pdf에서 HTML + JSON 출력
  - BeautifulSoup로 `<table>` 요소 추출
  - `table_html` 메타데이터에 HTML 저장
  - Markdown는 폴백용으로만 사용

### 2. **내용 기반 메타데이터 매칭**
- **문제**: HTML 테이블 수와 JSON 테이블 수가 다름
- **해결**:
  1. HTML 테이블 텍스트 추출
  2. JSON 테이블 텍스트 추출
  3. Jaccard 유사도 계산 (단어 중복 / 합집)
  4. 임계값 0.3 이상인 것만 매칭

### 3. **3단계 캐싱**
- **목적**: 반복 검색 시 성능 최적화
- **구현**:
  ```python
  # PDFTableSearch 클래스에서
  self.embeddings: SentenceTransformerEmbeddings  # 모델 한 번 로드
  self._cached_documents: dict[str, List[Document]]  # 문서 캐시
  self._loaded_pdfs: set[str]  # 벡터 저장소 추적
  ```

### 4. **지연 초기화**
- **목적**: 불필요한 리소스 낭비 방지
- **구현**:
  ```python
  # TableVectorStore 클래스에서
  @property
  def vectorstore(self) -> Chroma:
      if self._vectorstore is None:
          # 첫 호출 시에만 생성
          self._vectorstore = Chroma(...)
  ```

### 5. **LLM 폴백**
- **목적**: API 실패 시 사용자 경험 저하 방지
- **구현**:
  ```python
  # smart_search.py에서
  if selected_result is None and fallback_to_vector:
      return candidates_results[0]  # 벡터 #1 반환
  else:
      raise TableSearchError()  # 실패 시 예외 발생
  ```

### 6. **안전한 HTML 렌더링**
- **목적**: XSS 공격 방지
- **구현**:
  ```python
  def _sanitize_table_html(table_html: str) -> str:
      # - <script> 태그 제거
      # - 이벤트 핸들러 속성 제거 (onclick, onload 등)
      # - javascript: URL 제거
      # - 구조적 태그(tr, td, th) 보존
  ```

---

## ⚠️ 개선 필요 사항

### 1. **코드 리팩터링** (우선순위: 높음)

#### **loader.py (912줄)**
- ⚠️ **과도하게 긴 파일**: 여러 기능이 혼재
  - HTML 추출 로직
  - JSON 파싱 로직
  - 마크다운 변환 로직
  - 매칭 로직
  - **개선**: 각 기능을 별도 모듈로 분리

- ⚠️ **매칭 알고리즘 복잡성**:
  - 현재 Jaccard 유사도 계산이 복잡함
  - 단순 텍스트 포함으로 단순화 가능

#### **core.py** (494줄)
- ⚠️ **로직 중복**: 일부 로직이 단일/다중 문서 모드에서 중복
- **개선**: 공통 함수로 추출 (`_execute_search_with_rerank`)

### 2. **테스트 커버리지 확장** (중요: ⭐⭐⭐)

#### **누락된 모듈**
- ⚠️ **`reranker.py` 테스트 없음**: LLM 재랭킹 기능에 대한 단위 테스트 부재
- **개선**: `test_reranker.py` 추가

#### **추가 필요 테스트**
- ⚠️ **통합 파이프라인 테스트**: end-to-end 검색 흐름 테스트
- ⚠️ **Smart Search 테스트**: `smart_search()` 함수 통합 테스트
- ⚠️ **Edge case 테스트**:
  - 빈 PDF
  - 테이블이 없는 PDF
  - 아주 큰 PDF (>100MB)
  - 복잡한 colspan/rowspan
  - OCR 실패 시나리오

### 3. **문서화 개선**

#### **API 문서**
- ⚠️ **메서드 docstring 불완전**: 일부 함수에 상세 설명 누락
- ⚠️ **타입 힌트 부족**: 일부 파라미터에 타입 힌트 불충분
- **개선**: 전체 함수에 완전한 docstring 추가

#### **아키텍처 문서**
- ⚠️ **시퀀스 다이어그램 부족**: 모듈 간 데이터 흐름을 시각화한 다이어그램 부재
- **개선**: 현재 README에 있는 데이터 흐름 다이어그램 확장

### 4. **성능 최적화**

#### **메모리 관리**
- ⚠️ **문서 캐시 제한 없음**: 메모리 사용량 제어 필요
- ⚠️ **배치 크기 최적화**: 현재 `load_directory()`가 순차 처리
- **개선**: 병렬 처리 옵션 추가, 메모리 모니터링

#### **임베딩 최적화**
- ⚠️ **배치 임베딩**: 현재 개별 텍스트 임베딩
- **개선**: `embed_documents()`로 배치 처리 지원 확장

---

## 🎯 핵심 강점

1. ✅ **모듈형 아키텍처**: 책임 분리가 명확
2. ✅ **다중 임베딩 전략**: 상황에 따라 로컬/원격 선택 가능
3. ✅ **HTML 우선 접근**: 복잡한 테이블 구조 완벽 지원
4. ✅ **내용 기반 매칭**: 단순 인덱스 매칭보다 정확한 페이지 매핑
5. ✅ **안전한 렌더링**: XSS 방지 완료
6. ✅ **LLM 폴백**: API 실패 시 그레이스풀 경험
7. ✅ **캐싱 전략**: 3단계 캐싱으로 성능 최적화
8. ✅ **한국어 최적화**: BAAI/bge-m3 모델 사용

---

## 📝 요약

**PDFTableSearch**는 잘 설계된 모듈형 아키텍처를 가진 견고한 PDF 테이블 검색 라이브러리입니다.

**주요 특징**:
- 🏗️ **명확한 모듈 분리**: 각 모듈이 명확한 책임 가짐
- 🔍 **하이브리드 검색**: 벡터 검색 + LLM 선택 결합으로 정확도 극대화
- 🌐 **사용자 친화적 UI**: Streamlit로 직관적인 검색 환경 제공
- 🛡️ **안전한 설계**: XSS 방지, 경로 정제, 강력한 예외 처리
- ⚡ **확장성**: 모듈형 설계로 향후 기능 추가 용이
- 🚀 **성능 최적화**: 다단계 캐싱으로 반복 검색 성능 향상

**기술 스택**:
- PDF 처리: opendataloader-pdf, BeautifulSoup4
- 벡터 저장소: ChromaDB
- 임베딩: SentenceTransformers, z.ai API
- LLM 프레임워크: LangChain
- 웹 UI: Streamlit
- 테스트: pytest
- 코드 스타일: mypy, ruff

이 프로젝트는 **실무에서 사용 가능한 수준**으로 완성되어 있으며, 주요 개선이 필요한 부분은 **테스트 커버리지 확장**입니다.

---

## 🔄 개선 이력 (v0.2.0)

### 완료된 개선 사항

#### 1. 설정 관리 통합 — `config.py` (신규)
- pydantic-settings 기반 `Settings` 클래스로 모든 설정 통합
- 기존 8개 파일에 분산된 환경변수/하드코딩 기본값을 단일 소스로 관리
- `get_settings()` 싱글톤 접근자 제공
- `pyproject.toml`에 `pydantic-settings>=2.0.0` 추가

#### 2. LLM 응답 캐싱 — `llm_client.py` (수정)
- `LLMCache` 클래스 추가: 디스크 기반 SHA-256 해시 캐시
- 동일 query + table_descriptions 조합에 대해 API 호출 스킵
- 기본 TTL 24시간, `cache_dir` 설정 가능
- 반복 Smart Search 시 30-40초 → 2초 미만으로 단축

#### 3. 임베딩 프로바이더 추상화 — `embedding_provider.py` (신규)
- `create_embeddings("local"|"remote")` 팩토리 함수
- `ProviderType` 리터럴 타입
- 설정 하나로 로컬/원격 임베딩 전환 가능

#### 4. loader.py 모듈 분할 — `loader/` 패키지 (리팩터링)
- 기존 912줄 `loader.py` → 4개 서브모듈 + `__init__.py`
  - `html_parser.py`: HTML 테이블 추출, sanitize, HTML→MD 변환
  - `json_parser.py`: JSON 메타데이터 파싱
  - `markdown_parser.py`: 마크다운 테이블 추출, 제목/컨텍스트 파싱
  - `matcher.py`: HTML↔JSON 테이블 매칭 (Jaccard similarity)
- 기존 공개 API 100% 하위 호환 유지

#### 5. 병렬 로딩 — `core.py` (수정)
- `_load_all_documents_sequential` → `ThreadPoolExecutor` 기반 병렬 로딩
- 각 PDF마다 독립 `PDFProcessor` 인스턴스 사용 (상태 충돌 방지)
- 입력 순서 보장, 부분 실패 허용
- `parallel_workers` 설정으로 동시성 제어

#### 6. 증분 인덱싱 — `vectorstore.py` (수정)
- `add_documents(skip_existing=True)` 지원
- SHA-256 해시 기반 문서 중복 감지
- 이미 인덱싱된 문서 자동 스킵
- `TableVectorStore.get_or_create()` 싱글톤 팩토리
- 모듈 수준 인스턴스 캐시로 ChromaDB 연결 재사용

#### 7. 하이브리드 검색 (BM25 + Vector) — `hybrid_search.py` (신규)
- 키워드 기반 BM25 검색 + 벡터 유사도 검색 결합
- Reciprocal Rank Fusion (RRF)으로 결과 병합
- 정확한 숫자/고유명사 매칭 + 의미적 이해 동시 제공

#### 8. 테이블 QA — `table_qa.py` (신규)
- `ask_table(query, pdf_path)` 함수
- Smart Search로 최적 테이블 찾기 → LLM이 자연어 답변 생성
- 한국어 금융 문서에 최적화된 프롬프트

#### 9. 필터링 API — `core.py` (수정)
- `search_tables(filters={...})` 파라미터 추가
- 지원 필터: `page_range`, `min_rows`, `table_title_contains`, `document_name`

#### 10. REST API 서버 — `api.py` (신규)
- FastAPI 기반 HTTP API
- `POST /search`: PDF 업로드 후 테이블 검색
- `POST /ask`: PDF 업로드 후 자연어 질의응답
- `GET /health`: 상태 확인
- `pyproject.toml`에 `[api]` optional dependency 추가

### 파일 변경 요약

| 변경 유형 | 파일 | 설명 |
|-----------|------|------|
| 신규 | `config.py` | pydantic-settings 기반 통합 설정 |
| 신규 | `embedding_provider.py` | 임베딩 팩토리 |
| 신규 | `hybrid_search.py` | BM25 + Vector 하이브리드 검색 |
| 신규 | `table_qa.py` | 테이블 QA 기능 |
| 신규 | `api.py` | FastAPI REST 서버 |
| 신규 | `loader/__init__.py` | 로더 패키지 (PDFProcessor) |
| 신규 | `loader/html_parser.py` | HTML 테이블 추출 |
| 신규 | `loader/json_parser.py` | JSON 메타데이터 파싱 |
| 신규 | `loader/markdown_parser.py` | 마크다운 테이블 추출 |
| 신규 | `loader/matcher.py` | 테이블 매칭 |
| 수정 | `llm_client.py` | LLMCache 클래스 추가 |
| 수정 | `core.py` | 병렬 로딩, 필터링 API |
| 수정 | `vectorstore.py` | 증분 인덱싱, 싱글톤 팩토리 |
| 수정 | `__init__.py` | 새 모듈 export 추가 |
| 수정 | `pyproject.toml` | pydantic-settings, fastapi 의존성 추가 |
| 삭제 | `loader.py` | `loader/` 패키지로 대체 |
