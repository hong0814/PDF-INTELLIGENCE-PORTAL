# PDF 테이블 검색 시스템 아키텍처

## 개요

PDF 테이블 검색 시스템은 PDF 문서에서 테이블을 추출하고, 자연어 검색어를 통해 관련 테이블을 찾아주는 시스템입니다. 벡터 유사도 검색과 LLM 기반 테이블 선택을 결합하여 검색 정확도를 높입니다.

### 핵심 기능

- **PDF 테이블 추출**: opendataloader-pdf를 사용하여 PDF에서 테이블 추출
- **HTML 기반 처리**: 이중표(colspan/rowspan) 완벽 지원
- **벡터 검색**: SentenceTransformers 임베딩 + ChromaDB
- **Smart Search**: LLM 기반 테이블 재정렬
- **웹 인터페이스**: Streamlit 기반 검색 UI

---

## 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                         사용자                                    │
│                    (Streamlit 웹 UI)                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     검색 인터페이스                               │
│  - 검색어 입력                                                    │
│  - Smart Search 체크박스                                         │
│  - 결과 표시 (HTML 렌더링)                                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PDFTableSearch (메인)                           │
│  - 문서 로드 관리                                                │
│  - 캐싱 및 성능 최적화                                           │
└──────┬──────────────────────┬───────────────────────────────────┘
       │                      │
       ▼                      ▼
┌──────────────────┐  ┌──────────────────────────────────────┐
│  PDFProcessor    │  │     TableVectorStore                │
│  - PDF → HTML    │  │  - ChromaDB + 임베딩               │
│  - 테이블 추출    │  │  - 유사도 검색                     │
└──────────────────┘  └──────────────────────────────────────┘
                                  │
                                  ▼
                       ┌─────────────────────────────┐
                       │   Smart Search (선택 사항)    │
                       │  - 벡터 검색 (top_k 후보)     │
                       │  - LLM 테이블 선택           │
                       │  - 최적 결과 1개 반환        │
                       └─────────────────────────────┘
                                  │
                                  ▼
                       ┌─────────────────────────────┐
                       │       z.ai GLM-5.1 API       │
                       │    (LLM 재정렬/선택)          │
                       └─────────────────────────────┘
```

---

## 핵심 컴포넌트

### 1. PDFProcessor (`pdftablesearch/loader.py`)

PDF 문서를 처리하고 테이블을 추출하는 핵심 컴포넌트입니다.

#### 주요 기능

- **PDF 변환**: opendataloader-pdf를 사용하여 PDF → HTML + JSON 변환
- **HTML 테이블 추출**: BeautifulSoup을 사용하여 HTML에서 테이블 추출
- **제목 추출**: HTML `<h1>`~`<h6>` 태그에서 테이블 제목 추출
- **페이지 매핑**: 테이블 내용 기반 매칭으로 정확한 페이지 번호 매핑

#### 메서드

```python
processor = PDFProcessor()

# PDF 로드
result = processor.load_documents(
    pdf_path="report.pdf",
    use_hybrid=True,  # 하이브리드 모드 (더 정확한 테이블 추출)
)

# 추출된 문서 가져오기
documents = processor.get_documents()
```

### 2. TableVectorStore (`pdftablesearch/vectorstore.py`)

테이블의 벡터 인덱스를 생성하고 유사도 검색을 수행합니다.

#### 주요 기능

- **임베딩**: SentenceTransformers (distiluse-base-multilingual-cased-v2)
- **벡터 저장**: ChromaDB 영구 저장
- **유사도 검색**: 코사인 유사도 기반 검색

#### 메서드

```python
vector_store = TableVectorStore(
    embeddings=embeddings,
    persist_dir="./.chroma"
)

# 문서 추가
vector_store.add_documents(documents)

# 유사도 검색
results = vector_store.similarity_search(query="포괄손익계산서", k=5)
```

### 3. PDFTableSearch (`pdftablesearch/search.py`)

전체 검색 시스템을 조율하는 메인 클래스입니다.

#### 주요 기능

- **모델 캐싱**: 임베딩 모델을 한 번 로드하여 재사용
- **문서 캐싱**: 로드된 PDF 문서를 캐싱하여 빠른 검색
- **단일/다중 문서 검색**: 단일 PDF 또는 여러 PDF 검색 지원

#### 메서드

```python
searcher = PDFTableSearch()

# 단일 문서 검색
results = searcher.search(
    pdf_path="report.pdf",
    query="매출 증가율",
    max_results=5
)

# Smart Search
best_result = searcher.smart_search(
    pdf_path="report.pdf",
    query="가장 적합은 재무제표"
)
```

---

## 데이터 흐름

### 1. PDF 처리 파이프라인

```
PDF 파일
    ↓
opendataloader-pdf 변환
    ↓
┌─────────────────────────────────────┐
│  출력 파일들:                        │
│  - report.html (HTML 테이블)        │
│  - report.json (메타데이터)         │
└─────────────────────────────────────┘
    ↓
HTML 파싱 (BeautifulSoup)
    ↓
테이블 추출 + 제목 추출
    ↓
JSON 메타데이터 매칭 (페이지 번호)
    ↓
LangChain Document 생성
    ↓
벡터 저장 (ChromaDB)
```

### 2. 검색 파이프라인

```
사용자 검색어
    ↓
임베딩 (SentenceTransformers)
    ↓
벡터 검색 (ChromaDB)
    ↓
후보 테이블 (top_k)
    ↓
[Smart Search 선택 사항]
    ↓
LLM 테이블 선택 (z.ai GLM-5.1)
    ↓
최종 결과 반환
```

---

## HTML 기반 테이블 처리

### HTML 사용 이유

1. **이중표 지원**: colspan, rowspan 속성으로 병합 셀 표현
2. **구조화된 정보**: HTML 태그 구조로 표 계층 명확히 표현
3. **LLM 이해도**: 최신 LLM들이 HTML 구조를 잘 이해

### HTML 테이블 추적

```python
def _extract_html_tables_from_file(html_path: Path):
    soup = BeautifulSoup(content, "html.parser")
    tables = soup.find_all("table")

    for table_tag in tables:
        # 제목 추출 (이전 형제 노드)
        prev_heading = table_tag.find_previous_sibling(["h1", "h2", ..."])

        # HTML sanitization
        clean_html = _sanitize_table_html(str(table_tag))
```

### HTML 렌더링

```python
# Streamlit에서 HTML 렌더링
st.markdown(html_table, unsafe_allow_html=True)
```

---

## Smart Search (LLM 기반 테이블 선택)

### 작동 원리

1. **벡터 검색**: top_k(기본 20)개 후보 테이블 추출
2. **LLM 전달**: 후보 테이블을 HTML 형식으로 LLM에게 전달
3. **테이블 선택**: LLM이 가장 적합한 테이블 선택
4. **결과 반환**: 선택된 테이블 1개 + 추가 추천 2개

### LLM 프롬프트

```
시스템 프롬프트:
"당신은 금융 테이블 검색 전문가입니다.
HTML 테이블 구조(colspan, rowspan, th, td)를 분석하고,
사용자 검색어에 가장 적합한 테이블을 선택하세요."

사용자 프롬프트:
"검색어: {query}

테이블 후보:
1. (HTML 테이블)
2. (HTML 테이블)
...

가장 적합한 테이블의 인덱스와 신뢰도를 반환하세요."
```

---

## 페이지 번호 매핑

### 문제

- HTML: 모든 테이블 추출 (예: 15개)
- JSON: 일부 테이블만 인식 (예: 10개)
- 단순 인덱스 매칭 → 페이지 번호 오류

### 해결: 테이블 내용 기반 매칭

```python
# 1. HTML 테이블 텍스트 추출
html_content = _extract_table_text_content(html_table)

# 2. JSON 테이블과 유사도 계산
for json_meta in all_metadata:
    score = _calculate_table_similarity(html_content, json_meta)
    # 유사도 점수 계산 (텍스트 포함, 단어 중복)

# 3. 가장 유사한 JSON 테이블 매칭
best_match = max(all_metadata, key=lambda m: similarity(m))
page_number = best_match["page_number"]
```

---

## 검색 인터페이스

### Streamlit 웹 UI

**주요 기능:**
- PDF 파일 업로드 (다중 지원)
- 자연어 검색 입력
- Smart Search 체크박스
- 결과 테이블 HTML 렌더링
- 다운로드 (HTML, CSV)
- 디버그 모드 (검색 후보 표시)

**검색 옵션:**
- 최대 결과 수 (1-20)
- Smart Search 모드
- 모든 PDF 검색 / 특정 PDF 검색

### 실행 방법

```bash
# 웹 데모 실행
./run_web_demo.sh

# 또는 직접 실행
streamlit run streamlit_app.py --server.port 8501
```

---

## 기술 스택

### 핵심 라이브러리

| 컴포넌트 | 라이브러리 | 용도 |
|----------|-----------|------|
| PDF 변환 | opendataloader-pdf | PDF → HTML + JSON |
| HTML 파싱 | BeautifulSoup4 | HTML 테이블 추출 |
| 임베딩 | SentenceTransformers | 텍스트 → 벡터 |
| 벡터 저장 | ChromaDB | 벡터 인덱스 저장 |
| LLM | z.ai GLM-5.1 API | 테이블 선택 |
| 웹 UI | Streamlit | 검색 인터페이스 |

### 의존성

```
pdftablesearch/
├── opendataloader-pdf    # PDF 변환
├── beautifulsoup4         # HTML 파싱
├── sentence-transformers  # 임베딩
├── chromadb               # 벡터 DB
├── langchain              # LLM 프레임워크
├── streamlit              # 웹 UI
└── openai                 # LLM API 클라이언트
```

---

## 배포 및 실행

### 환경 설정

```bash
# Python 3.11
python3.11 -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -e .
```

### 실행

```bash
# 웹 데모
./run_web_demo.sh

# CLI
python -m pdftablesearch.smart_search_cli \
  --pdf report.pdf \
  --query "포괄손익계산서" \
  --top-k 20
```

### 환경 변수

```bash
# z.ai API 키 (필수)
export ZAI_API_KEY="your-api-key"

# 선택적 설정
export PDFTABLESEARCH_MODEL="distiluse-base-multilingual-cased-v2"
export PDFTABLESEARCH_CHROMA_DIR="./.chroma"
```

---

## 성능 최적화

### 캐싱 전략

1. **임베딩 모델 캐싱**: 한 번 로드하여 재사용
2. **문서 캐싱**: 로드된 PDF 문서를 메모리에 저장
3. **벡터 저장 캐싱**: ChromaDB 영구 저장

### 검색 성능

- **첫 검색**: ~3-5초 (PDF 변환 + 임베딩 + 벡터 검색)
- **이후 검색**: ~1-2초 (임베딩 캐시 + 벡터 검색)
- **Smart Search**: ~30-40초 (벡터 검색 + LLM 호출)

---

## 향후 개선 사항

1. **테이블 OCR**: 테이블이 이미지로 저장된 경우 OCR 처리
2. **다중 언어 지원**: 영어, 중국어 등 추가 언어 지원
3. **배치 처리**: 여러 PDF 동시 처리
4. **API 서버**: REST API로 검색 서비스 제공
5. **테이블 병합**: 분할된 테이블 자동 병합

---

## 문서

- **CLAUDE.md**: 프로젝트 개요 및 개발 가이드
- **smart_search_architecture.md**: 본 문서 (아키텍처 상세)
- **README.md**: 설치 및 사용법

---

## 라이선스

Proprietary - Internal Use Only

---

*마지막 업데이트: 2026년 4월 21일*
