# PDFTableSearch

PDF 문서에서 표를 의미적으로 검색하는 Python 라이브러리

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![LangChain](https://img.shields.io/badge/langchain-0.1.0-green.svg)](https://github.com/langchain-ai/langchain)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 📋 목차

- [개요](#-개요)
- [주요 기능](#-주요-기능)
- [아키텍처](#-아키텍처)
- [사용자 플로우](#-사용자-플로우)
- [빠른 시작](#-빠른-시작)
- [설치](#-설치)
- [상세 사용법](#-상세-사용법)
- [API 레퍼런스](#-api-레퍼런스)
- [구성](#-configuration)
- [트러블슈팅](#-트러블슈팅)
- [FAQ](#-faq)
- [기여](#-기여)
- [라이선스](#-라이선스)

---

## 🎯 개요

**PDFTableSearch**는 PDF 문서에 포함된 표를 자연어 질문으로 검색할 수 있는 Python 라이브러리입니다. LangChain 프레임워크와 벡터 데이터베이스(ChromaDB)를 활용하여 문맥을 이해하고 관련 표를 찾아줍니다.

### 왜 PDFTableSearch인가요?

- **의미적 검색**: 단순 키워드 매칭이 아닌 의미를 이해하고 검색
- **다중 문서 지원**: 여러 PDF에서 동시에 표 검색
- **한국어 완벽 지원**: 한국어 질문과 문서 완벽 처리
- **간단한 API**: 단일 함수로 단일/다중 문서 검색
- **프로덕션 준비**: 견고한 에러 처리와 로깅

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| 🔍 **의미적 검색** | 자연어 질문으로 표 검색 (벡터 유사도 기반) |
| 📄 **단일/다중 문서** | 하나 또는 여러 PDF에서 동시 검색 |
| 🤖 **LLM 재랭킹** | 선택적 LLM 기반 결과 재정렬으로 정확도 향상 |
| 🚀 **빠른 검색** | ChromaDB 벡터 저장소로 초고속 검색 |
| 📊 **완전한 메타데이터** | 페이지 번호, 좌표, 문서명 포함 |
| 🔄 **배치 처리** | 여러 PDF를 병렬로 처리 |
| 💾 **영구 저장** | 벡터 인덱스를 디스크에 저장하여 빠른 재검색 |

---

## 🏗️ 아키텍처

### 시스템 구조도

```
┌─────────────────────────────────────────────────────────────────────┐
│                         사용자 (User)                               │
│  "2024년 연간 매출이 가장 높은 제품은?"                            │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PDFTableSearch API                               │
│                                                                     │
│  search_tables(                                                    │
│      pdf_path = "report.pdf",        # 또는 ["doc1.pdf", "doc2"]   │
│      query = "연간 매출",                                            │
│      max_results = 5                                               │
│  )                                                                 │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │ PDFProcessor  │   │ ZaiEmbeddings │   │ TableVector   │
    │               │   │               │   │ Store         │
    │ • PDF 로드    │   │ • 임베딩 생성 │   │ • ChromaDB    │
    │ • 테이블 추출 │   │ • z.ai API    │   │ • 유사도 검색 │
    └───────────────┘   └───────────────┘   └───────────────┘
                │                   │                   │
                ▼                   ▼                   ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                      처리 파이프라인                            │
    │                                                                  │
    │  1. PDF → Documents (opendataloader-pdf)                       │
    │  2. 테이블 추출 + 메타데이터 파싱                               │
    │  3. 텍스트 임베딩 (z.ai API)                                     │
    │  4. ChromaDB에 저장                                             │
    │  5. 쿼리 임베딩                                                 │
    │  6. 코사인 유사도 검색                                           │
    │  7. (선택) LLM 재랭킹                                           │
    │  8. 결과 반환                                                   │
    └─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          검색 결과                                  │
│                                                                    │
│  [                                                                │
│    {                                                              │
│      "table_id": "table_5_2",                                     │
│      "document_name": "report.pdf",                               │
│      "page_number": 5,                                            │
│      "bounding_box": [100, 200, 500, 700],                        │
│      "table_markdown": "| 제품 | 매출 |...",                       │
│      "relevance_score": 0.95                                      │
│    }                                                              │
│  ]                                                                │
└─────────────────────────────────────────────────────────────────────┘
```

### 핵심 컴포넌트

#### 1. PDFProcessor
PDF 문서를 로드하고 테이블을 추출하는 컴포넌트입니다.

```python
from pdftablesearch import PDFProcessor

processor = PDFProcessor()
docs = processor.load_documents("report.pdf")
```

**기능:**
- opendataloader-pdf를 사용하여 PDF를 LangChain Document로 변환
- Markdown 형식의 테이블 추출
- 페이지 번호, 바운딩 박스 좌표 등 메타데이터 추출
- 배치 처리 지원 (병렬 로딩)

#### 2. ZaiEmbeddings
LangChain Embeddings 인터페이스를 구현한 z.ai 임베딩 클래스입니다.

```python
from pdftablesearch import ZaiEmbeddings

embeddings = ZaiEmbeddings(api_key="your-key")
vector = embeddings.embed_query("연간 매출 현황")
```

**기능:**
- z.ai API를 사용한 텍스트 임베딩
- LangChain과 완벽 호환
- 한글/영어 지원
- 자동 재시도 및 에러 처리

#### 3. TableVectorStore
ChromaDB 기반 벡터 저장소 관리 클래스입니다.

```python
from pdftablesearch import TableVectorStore, ZaiEmbeddings

store = TableVectorStore(
    embedding_function=ZaiEmbeddings(),
    persist_directory="./.chroma"
)
store.add_documents(documents)
results = store.search("매출", k=5)
```

**기능:**
- ChromaDB 벡터 저장소 관리
- 영구 저장 및 로드
- 문서 필터링 (문서별 검색)
- 유사도 검색

#### 4. ZaiRerankCompressor
선택적 LLM 재랭킹 컴포넌트입니다.

```python
from pdftablesearch import ZaiRerankCompressor

compressor = ZaiRerankCompressor(llm=zai_llm)
reranked_docs = compressor.compress_documents(documents, query)
```

**기능:**
- z.ai LLM을 사용한 결과 재정렬
- 검색 정확도 향상
- Graceful fallback (LLM 실패 시 벡터 결과 사용)

### 데이터 흐름도

```
┌──────────────┐
│  PDF 파일    │
└──────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    opendataloader-pdf                          │
│  • PDF → Markdown 변환                                          │
│  • PDF → JSON 메타데이터                                        │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PDFProcessor                               │
│  • Markdown에서 테이블 추출 (정규식)                             │
│  • JSON에서 메타데이터 추출                                     │
│  • LangChain Document 생성                                      │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Document 목록                                │
│  [                                                             │
│    Document(                                                   │
│      page_content = "| 제품 | 매출 |...",                       │
│      metadata = {                                              │
│        "table_id": "table_5_2",                                │
│        "document_name": "report.pdf",                          │
│        "page_number": 5,                                       │
│        "bounding_box": [100, 200, 500, 700]                    │
│      }                                                         │
│    ),                                                          │
│    ...                                                         │
│  ]                                                             │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ZaiEmbeddings                                │
│  • 각 Document의 page_content를 임베딩                         │
│  • z.ai API 호출                                               │
│  • 임베딩 벡터 반환                                            │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TableVectorStore                             │
│  • ChromaDB에 임베딩 + 메타데이터 저장                         │
│  • 영구 저장 (./.chroma/)                                       │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      검색 요청                                  │
│  query = "2024년 연간 매출이 가장 높은 제품은?"                │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    쿼리 임베딩                                  │
│  • query를 ZaiEmbeddings로 임베딩                              │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                   코사인 유사도 검색                            │
│  • ChromaDB similarity_search_with_score                        │
│  • 상위 K개 결과 반환                                           │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                (선택) LLM 재랭킹                               │
│  • ZaiRerankCompressor로 재정렬                               │
│  • 정확도 향상                                                  │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      결과 반환                                  │
│  • TableSearchResult 목록                                      │
│  • 테이블 마크다운 + 메타데이터 + 점수                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔄 사용자 플로우

### 1단계: 설치

```bash
# pip로 설치
pip install pdftablesearch

# 또는 개발 버전 설치
pip install -e git+https://github.com/yourusername/pdftablesearch.git
```

### 2단계: 환경 설정

```bash
# .env 파일 생성
cat > .env << EOF
ZAI_API_KEY=your_api_key_here
CHROMA_PERSIST_DIR=./.chroma
EOF
```

### 3단계: 기본 검색 (단일 문서)

```python
from pdftablesearch import search_tables

# PDF에서 표 검색
results = search_tables(
    pdf_path="financial_report.pdf",
    query="2024년 연간 매출 현황",
    max_results=3
)

# 결과 확인
for table in results:
    print(f"문서: {table.document_name}")
    print(f"페이지: {table.page_number}")
    print(f"관련도: {table.relevance_score:.2f}")
    print(f"표:\n{table.table_markdown}\n")
```

### 4단계: 다중 문서 검색

```python
from pdftablesearch import search_tables

# 여러 PDF에서 동시 검색
results = search_tables(
    pdf_path=["report_2023.pdf", "report_2024.pdf"],
    query="매출 성장률",
    max_results=10,
    max_results_per_doc=3
)

# 결과 확인
for table in results:
    print(f"[{table.document_name}] 페이지 {table.page_number}")
    print(f"관련도: {table.relevance_score:.2f}")
```

### 5단계: LLM 재랭킹 사용 (선택)

```python
# LLM 재랭킹으로 더 정확한 결과
results = search_tables(
    pdf_path="report.pdf",
    query="영업이익이 가장 높은 사업부는?",
    max_results=5,
    use_llm_rerank=True  # LLM 재랭킹 활성화
)

# 재랭킹 점수 확인
for table in results:
    if table.rerank_score:
        print(f"벡터 점수: {table.relevance_score:.2f}")
        print(f"재랭킹 점수: {table.rerank_score:.2f}")
```

### 6단계: 진행 상황 모니터링

```python
from pdftablesearch import PDFProcessor
from tqdm import tqdm

# 진행 콜백 함수
def progress_callback(current, total, filename, status):
    print(f"[{current}/{total}] {filename}: {status}")

# 배치 처리
processor = PDFProcessor()
result = processor.load_documents_batch(
    pdf_paths=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
    progress_callback=progress_callback
)

print(f"총 {result.total_tables}개 테이블 추출 완료")
```

---

## 🚀 빠른 시작

### 5분 만에 시작하기

```bash
# 1. 설치
pip install pdftablesearch

# 2. API 키 설정
export ZAI_API_KEY="your_api_key"

# 3. Python 실행
python << EOF
from pdftablesearch import search_tables

# PDF에서 표 검색
results = search_tables(
    pdf_path="report.pdf",
    query="연간 매출",
    max_results=3
)

# 결과 출력
for i, table in enumerate(results, 1):
    print(f"\n=== 결과 {i} ===")
    print(f"문서: {table.document_name}")
    print(f"페이지: {table.page_number}")
    print(f"관련도: {table.relevance_score:.2f}")
    print(f"표:\n{table.table_markdown}")
EOF
```

---

## 📦 설치

### 요구사항

- Python 3.11 이상
- pip 또는 poetry

### pip로 설치

```bash
pip install pdftablesearch
```

### 개발 버전 설치

```bash
git clone https://github.com/yourusername/pdftablesearch.git
cd pdftablesearch
pip install -e .
```

### 의존성

자동으로 설치되는 의존성:

```
langchain>=0.1.0
langchain-community>=0.0.20
langchain-openai>=0.0.5
opendataloader-pdf>=1.0.0
chromadb>=0.4.0
requests>=2.31.0
pydantic>=2.5.0
python-dotenv>=1.0.0
tenacity>=8.2.0
tqdm>=4.66.0
```

---

## 📖 상세 사용법

### 단일 문서 검색

```python
from pdftablesearch import search_tables

# 기본 검색
results = search_tables(
    pdf_path="report.pdf",
    query="매출 현황"
)

# 결과 수 제한
results = search_tables(
    pdf_path="report.pdf",
    query="매출 현황",
    max_results=5
)

# LLM 재랭킹 사용
results = search_tables(
    pdf_path="report.pdf",
    query="영업이익이 가장 높은 사업부",
    use_llm_rerank=True
)

# 커스텀 API 키
results = search_tables(
    pdf_path="report.pdf",
    query="재무제표",
    api_key="custom_api_key"
)

# 커스텀 ChromaDB 경로
results = search_tables(
    pdf_path="report.pdf",
    query="비용 구조",
    chroma_persist_dir="./my_vectorstore"
)
```

### 다중 문서 검색

```python
from pdftablesearch import search_tables

# 여러 문서 검색
results = search_tables(
    pdf_path=["report_2023.pdf", "report_2024.pdf"],
    query="매출 성장"
)

# 문서별 결과 수 제한
results = search_tables(
    pdf_path=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
    query="재무 현황",
    max_results_per_doc=2  # 각 문서에서 최대 2개
)

# 전체 결과 수 제한
results = search_tables(
    pdf_path=["doc1.pdf", "doc2.pdf"],
    query="시장 점유율",
    max_results=10  # 전체 최대 10개
)
```

### 결과 처리

```python
from pdftablesearch import search_tables

results = search_tables("report.pdf", "매출")

# 단일 문서 검색 결과 (List[TableSearchResult])
for table in results:
    print(f"표 ID: {table.table_id}")
    print(f"문서: {table.document_name}")
    print(f"페이지: {table.page_number}")
    print(f"좌표: {table.bounding_box}")
    print(f"관련도: {table.relevance_score}")
    print(f"표:\n{table.table_markdown}\n")

# 다중 문서 검색 결과 (MultiDocumentSearchResult)
if isinstance(results, MultiDocumentSearchResult):
    print(f"총 결과: {results.total_results}")
    print(f"문서별 결과:")
    for doc_name, count in results.document_counts.items():
        print(f"  {doc_name}: {count}개")
    
    # 특정 문서 결과만 필터링
    specific_docs = results.filter_by_document("report_2024.pdf")
```

### PDFProcessor 직접 사용

```python
from pdftablesearch import PDFProcessor

processor = PDFProcessor()

# 단일 문서 로드
result = processor.load_documents("report.pdf")
print(f"로드된 문서: {result.documents_loaded}")
print(f"추출된 테이블: {result.tables_extracted}")

# 여러 문서 로드 (병렬)
result = processor.load_documents_batch(
    pdf_paths=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
    parallel_workers=4
)
print(f"성공: {len(result.successful)}")
print(f"실패: {len(result.failed)}")
print(f"총 테이블: {result.total_tables}")

# 디렉토리 내 모든 PDF 로드
result = processor.load_directory(
    input_dir="./reports",
    recursive=True
)
```

### LangChain 직접 사용 (고급)

```python
from pdftablesearch import (
    PDFProcessor,
    ZaiEmbeddings,
    TableVectorStore
)
from langchain_community.vectorstores import Chroma

# 1. 문서 로드
processor = PDFProcessor()
docs = processor.load_documents("report.pdf")

# 2. 임베딩 함수 생성
embeddings = ZaiEmbeddings(api_key="your-key")

# 3. 벡터 저장소 생성
vectorstore = Chroma.from_documents(
    documents=docs,
    embedding=embeddings,
    persist_directory="./.chroma"
)

# 4. 검색
results = vectorstore.similarity_search_with_score(
    query="매출 현황",
    k=5
)

for doc, score in results:
    print(f"점수: {score}")
    print(f"페이지: {doc.metadata['page_number']}")
    print(f"내용: {doc.page_content[:100]}...")
```

---

## 📚 API 레퍼런스

### search_tables()

PDF 문서에서 표를 검색합니다.

```python
search_tables(
    pdf_path: Union[str, List[str]],
    query: str,
    max_results: int = 5,
    max_results_per_doc: Optional[int] = None,
    use_llm_rerank: bool = False,
    chroma_persist_dir: str = "./.chroma",
    api_key: Optional[str] = None
) -> Union[List[TableSearchResult], MultiDocumentSearchResult]
```

**파라미터:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `pdf_path` | `str` 또는 `List[str]` | 필수 | 단일 PDF 경로 또는 여러 PDF 경로 목록 |
| `query` | `str` | 필수 | 검색 쿼리 (한국어 또는 영어) |
| `max_results` | `int` | `5` | 최대 결과 수 |
| `max_results_per_doc` | `int` | `None` | 다중 문서 시 문서별 최대 결과 수 |
| `use_llm_rerank` | `bool` | `False` | LLM 재랭킹 사용 여부 |
| `chroma_persist_dir` | `str` | `"./.chroma"` | ChromaDB 저장 경로 |
| `api_key` | `str` | `None` | z.ai API 키 (환경변수 우선) |

**반환값:**

- 단일 문서: `List[TableSearchResult]`
- 다중 문서: `MultiDocumentSearchResult`

**예외:**

- `FileNotFoundError`: PDF 파일을 찾을 수 없음
- `TableSearchError`: 검색 실패
- `APIError`: z.ai API 호출 실패

### TableSearchResult

단일 검색 결과를 나타내는 데이터 클래스입니다.

```python
@dataclass
class TableSearchResult:
    table_id: str                              # 표 ID (예: "table_5_2")
    document_name: str                         # 문서 이름
    page_number: int                           # 페이지 번호
    bounding_box: List[int]                    # 좌표 [x1, y1, x2, y2]
    table_markdown: str                        # 표 마크다운
    relevance_score: Optional[float]           # 벡터 유사도 점수
    rerank_score: Optional[float]             # LLM 재랭킹 점수
```

### MultiDocumentSearchResult

다중 문서 검색 결과를 나타내는 데이터 클래스입니다.

```python
@dataclass
class MultiDocumentSearchResult:
    results: List[TableSearchResult]           # 검색 결과 목록
    document_counts: Dict[str, int]           # 문서별 결과 수
    total_results: int                         # 전체 결과 수
    query: str                                 # 검색 쿼리
```

**메서드:**

- `filter_by_document(document_name: str)`: 특정 문서 결과만 필터링

### PDFProcessor

PDF 문서 로딩 및 처리를 담당하는 클래스입니다.

```python
processor = PDFProcessor(
    chroma_persist_dir: str = "./.chroma",
    parallel_workers: int = 4
)
```

**메서드:**

- `load_documents(pdf_path: str)`: 단일 문서 로드
- `load_documents_batch(pdf_paths: List[str])`: 여러 문서 병렬 로드
- `load_directory(input_dir: str, recursive: bool = False)`: 디렉토리 로드

---

## ⚙️ Configuration

### 환경 변수

| 변수 | 설명 | 필수 | 기본값 |
|------|------|------|--------|
| `ZAI_API_KEY` | z.ai API 키 | 필수 | - |
| `CHROMA_PERSIST_DIR` | ChromaDB 저장 경로 | 선택 | `./.chroma` |
| `PDFTABLESEARCH_LOG_LEVEL` | 로그 레벨 | 선택 | `INFO` |
| `PDFTABLESEARCH_MAX_PARALLEL_WORKERS` | 최대 병렬 작업자 수 | 선택 | `4` |
| `PDFTABLESEARCH_API_TIMEOUT` | API 타임아웃 (초) | 선택 | `30` |

### .env 파일 예시

```bash
# 필수
ZAI_API_KEY=d464ac631e2147198f2bda6a27d6c84f.xyAUTLiGiy2ll1hb

# 선택
CHROMA_PERSIST_DIR=./.chroma
PDFTABLESEARCH_LOG_LEVEL=DEBUG
PDFTABLESEARCH_MAX_PARALLEL_WORKERS=8
PDFTABLESEARCH_API_TIMEOUT=60
```

---

## 🔧 트러블슈팅

### 문제: "API key not found"

**해결:**
```bash
# 환경 변수 설정
export ZAI_API_KEY="your_api_key"

# 또는 .env 파일 생성
echo "ZAI_API_KEY=your_api_key" > .env
```

### 문제: "PDF file not found"

**해결:**
```python
# 파일 존재 확인
from pathlib import Path
pdf_path = Path("report.pdf")
if not pdf_path.exists():
    raise FileNotFoundError(f"PDF not found: {pdf_path}")

# 절대 경로 사용
import os
pdf_path = os.path.abspath("report.pdf")
```

### 문제: 검색 결과가 없음

**해결:**
```python
# 1. 더 많은 결과 요청
results = search_tables(
    pdf_path="report.pdf",
    query="매출",
    max_results=20  # 증가
)

# 2. LLM 재랭킹 사용
results = search_tables(
    pdf_path="report.pdf",
    query="매출",
    use_llm_rerank=True  # 활성화
)

# 3. 쿼리 재작성
# "매출" → "연간 매출 현황" 또는 "revenue"
```

### 문제: 속도가 느림

**해결:**
```python
# 1. 병렬 처리 증가
processor = PDFProcessor(parallel_workers=8)

# 2. LLM 재랭킹 비활성화
results = search_tables(
    pdf_path="report.pdf",
    query="매출",
    use_llm_rerank=False  # 비활성화
)

# 3. ChromaDB 캐시 확인
# 첫 검색 후 벡터 인덱스가 생성되면 빠름
```

### 문제: 메모리 부족

**해결:**
```python
# 1. 배치 크기 줄이기
result = processor.load_documents_batch(
    pdf_paths=large_file_list,
    parallel_workers=1  # 줄이기
)

# 2. 문서별 검색
for pdf in pdf_list:
    results = search_tables(pdf, "query")
```

---

## ❓ FAQ

### Q: 한글과 영어를 함께 사용할 수 있나요?

A: 네, 한국어와 영어를 모두 지원합니다. 쿼리와 문서가 혼합된 언어여도 작동합니다.

```python
# 모두 작동
search_tables("report.pdf", "연간 매출")
search_tables("report.pdf", "annual revenue")
search_tables("report.pdf", "연간 revenue 현황")
```

### Q: PDF의 모든 표를 검색 대상으로 포함하나요?

A: 네, opendataloader-pdf가 추출한 모든 표를 인덱싱합니다. 이미지로 된 표는 OCR을 통해 텍스트로 변환됩니다.

### Q: 검색 결과의 정확도를 높이려면?

A: LLM 재랭킹을 활성화하세요.

```python
results = search_tables(
    pdf_path="report.pdf",
    query="복잡한 질문",
    use_llm_rerank=True  # 정확도 향상
)
```

### Q: 대용량 PDF를 처리하는데 얼마나 걸리나요?

A: 일반적으로 100페이지 PDF는 1-2분 내에 처리됩니다. 첫 검색 후 벡터 인덱스가 생성되면 이후 검색은 1-2초 내에 완료됩니다.

### Q: 여러 사용자가 동시에 사용할 수 있나요?

A: ChromaDB는 로컬 파일 기반이므로 단일 사용자용입니다. 다중 사용자 환경에서는 원격 벡터 DB(PostgreSQL + pgvector, Pinecone 등)로 마이그레이션이 필요합니다.

### Q: 오프라인에서 사용할 수 있나요?

A: 첫 인덱싱 시 z.ai API가 필요하지만, 이후에는 오프라인으로 검색할 수 있습니다. 완전히 오프라인하려면 로컬 임베딩 모델(sentence-transformers)을 사용하도록 수정해야 합니다.

### Q: 검색 캐싱을 지원하나요?

A: 네, ChromaDB가 벡터 인덱스를 영구 저장하므로 동일 쿼리는 매우 빠르게 재검색됩니다.

### Q: 특정 페이지만 검색할 수 있나요?

A: 현재는 전체 문서 검색만 지원합니다. 페이지 필터링은 향후 업데이트에서 추가될 예정입니다.

---

## 🤝 기여

기여를 환영합니다! 다음 단계를 따라주세요:

1. 리포지토리를 포크합니다
2. 기능 브랜치를 생성합니다 (`git checkout -b feature/amazing-feature`)
3. 변경사항을 커밋합니다 (`git commit -m 'Add amazing feature'`)
4. 브랜치에 푸시합니다 (`git push origin feature/amazing-feature`)
5. Pull Request를 엽니다

### 개발 환경 설정

```bash
# 클론
git clone https://github.com/yourusername/pdftablesearch.git
cd pdftablesearch

# 가상 환경
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 개발 의존성 설치
pip install -e ".[dev]"

# 테스트 실행
pytest

# 코드 스타일 검사
black pdftablesearch/
mypy pdftablesearch/
```

---

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 확인하세요.

---

## 📞 지원

- 이메일: support@pdftablesearch.io
- GitHub Issues: https://github.com/yourusername/pdftablesearch/issues
- 문서: https://docs.pdftablesearch.io

---

## 🌟 Acknowledgments

- [LangChain](https://github.com/langchain-ai/langchain) - 강력한 LLM 프레임워크
- [ChromaDB](https://github.com/chroma-core/chroma) - 오픈소스 벡터 데이터베이스
- [opendataloader-pdf](https://github.com/opendataloader/pdf) - PDF 처리 라이브러리
- [z.ai](https://z.ai) - AI API 제공

---

**PDFTableSearch로 PDF 문서의 표를 쉽고 빠르게 검색하세요! 🚀**
