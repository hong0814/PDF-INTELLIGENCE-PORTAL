# PDF Intelligence Portal

PDF 문서에서 표와 텍스트를 의미적으로 검색하고, AI 기반 질의응답을 통해 문서를 분석하는 웹 애플리케이션입니다.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![LangChain](https://img.shields.io/badge/langchain-0.1.0-green.svg)](https://github.com/langchain-ai/langchain)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-0.4.0-orange.svg)](https://www.trychroma.com/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

## 목차

- [개요](#-개요)
- [주요 기능](#-주요-기능)
- [시스템 아키텍처](#-시스템-아키텍처)
- [화면 구성](#-화면-구성)
- [빠른 시작](#-빠른-시작)
- [상세 실행 방법](#-상세-실행-방법)
- [프로젝트 구조](#-프로젝트-구조)
- [기술 스택](#-기술-스택)
- [트러블슈팅](#-트러블슈팅)
- [라이선스](#-라이선스)

---

## 개요

**PDF Intelligence Portal**은 금융 문서(신용심사, PF대출, 재무제표 등)를 업로드하고 자연어로 검색할 수 있는 AI 기반 문서 분석 도구입니다. 기존의 단순 키워드 검색을 넘어, **의미적 검색 + LLM 기반 질의응답**을 통해 문서 내용을 정확하게 파악할 수 있습니다.

### 왜 PDF Intelligence Portal인가요?

| 특징 | 설명 |
|------|------|
| **의미적 검색** | 단순 키워드 매칭이 아닌 문맥을 이해하고 검색 |
| **다중 문서 지원** | 여러 PDF를 동시에 업로드하고 선택적으로 검색 |
| **PDF 내 하이라이트** | 검색 결과의 출처 페이지에서 매칭된 부분을 시각적으로 강조 |
| **한국어 완벽 지원** | 한국어 질문과 문서를 완벽하게 처리 |
| **세션 관리** | 여러 세션을 생성하고 전환하며 독립적인 작업 환경 유지 |
| **세션 간 기록 유지** | 세션을 전환해도 이전 검색 기록이 그대로 보존 |

---

## 주요 기능

### 1. 표 검색 (Table Search)

PDF 문서에서 추출된 표를 의미적으로 검색합니다. ChromaDB 벡터 데이터베이스와 로컬 임베딩 모델을 사용하여 관련성 높은 표를 찾아줍니다.

**Smart Search 모드**: 검색된 여러 표 중 AI(LLM)가 가장 관련성 높은 표 하나를 자동으로 선택해 보여줍니다.

### 2. 텍스트 검색 (Document QA)

문서 전체 내용을 기반으로 자연어 질문에 답변합니다. 검색된 문서 청크를 RAG(Retrieval-Augmented Generation) 방식으로 LLM에게 전달하여 정확한 답변을 생성합니다.

- 벡터 검색 + BM25 키워드 검색의 하이브리드 검색 (RRF Fusion)
- 답변에 사용된 출처 페이지 링크 제공
- 출처 페이지에서 매칭된 텍스트 하이라이트 표시

### 3. 문서 보기 (Document Viewer)

업로드된 PDF를 페이지 단위로 열람할 수 있습니다. pdf.js를 사용한 고화질 렌더링과 함께, 추출된 표의 위치를 오버레이로 표시합니다. 검색 결과에서 특정 표를 클릭하면 해당 페이지로 이동하여 bounding box 영역이 하이라이트됩니다.

### 4. 기업금융심사 (Credit Review)

PDF에서 추출된 이미지(차트, 도표 등)를 주변 텍스트 컨텍스트와 함께 확인할 수 있는 특화 뷰입니다. 금융 문서의 시각적 데이터를 효율적으로 검토할 수 있습니다.

### 5. 세션 관리

- **세션 생성/전환/삭제**: 여러 독립적인 작업 환경을 관리
- **검색 기록 유지**: 세션을 전환해도 각 세션의 표 검색 결과와 QA 대화 기록이 localStorage에 보존
- **PDF 선택 필터링**: 여러 PDF 중 원하는 문서만 선택하여 검색 범위 제한

---

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│                        사용자 (Browser)                          │
│                  http://localhost:8000                           │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    React Frontend (Vite + TypeScript)            │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ Main     │ │ Document │ │ Search   │ │ QA Panel │           │
│  │ Screen   │ │ Viewer   │ │ Results  │ │(Text)    │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│                                                                  │
│  State Management: Zustand (useAppStore)                        │
│  Styling: Tailwind CSS v4                                       │
└──────────────────────────────────────────────────────────────────┘
                                │ HTTP/SSE
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                  FastAPI Backend (Python 3.11)                   │
│                                                                  │
│  POST /api/upload          - PDF 업로드 & 테이블 추출            │
│  POST /api/search          - 표 검색 (벡터 유사도)               │
│  POST /api/smart-search    - AI 표 선택 검색 (SSE 스트리밍)      │
│  POST /api/ask-document    - 문서 QA (RAG + LLM, SSE 스트리밍)   │
│  POST /api/qa              - 표 Q&A (SSE 스트리밍)               │
│  GET/POST/DELETE /api/sessions - 세션 관리                       │
│  GET  /api/documents/*     - PDF/HTML/이미지 서빙                 │
│                                                                  │
│  Session Storage: In-Memory Dict (tempfile 기반)                │
└──────────────────────────────────────────────────────────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│ opendataloader-pdf│ │ SentenceTransformers│ │  ChromaDB         │
│ (PDF → HTML/JSON) │ │ (로컬 임베딩)       │ │ (벡터 저장소)     │
│                   │ │ BAAI/bge-m3        │ │                   │
│ Hybrid Mode:      │ │                    │ │ Table Store       │
│ docling-fast       │ │                    │ │ Doc Chunk Store   │
│ (OCR 기반)        │ │                    │ │                   │
└───────────────────┘ └───────────────────┘ └───────────────────┘
            │                                       │
            ▼                                       ▼
┌───────────────────┐                   ┌───────────────────┐
│   z.ai LLM API    │                   │   BM25 Index       │
│   glm-4.7         │                   │   (키워드 검색)    │
│   (LLM 응답 생성) │                   └───────────────────┘
└───────────────────┘
```

### 데이터 처리 파이프라인

```
PDF 업로드
  → opendataloader-pdf 변환 (hybrid=docling-fast, OCR 지원)
  → HTML 파일 생성 (페이지 구분자 포함)
  → HTML에서 <table> 태그 추출 (BeautifulSoup)
  → JSON 메타데이터 매칭 (페이지 번호, bounding box)
  → LangChain Document 생성 (table_html + metadata)
  → SentenceTransformer 임베딩 (bge-m3, 로컬 CPU)
  → ChromaDB 저장 (벡터 인덱스)

문서 청킹 (텍스트 검색용)
  → HTML에서 표 제거 + 페이지 구분자로 분할
  → RecursiveCharacterTextSplitter (1000자 청크)
  → ChromaDB 저장 (doc_chunks 컬렉션)
  → BM25 인덱스 생성 (한국어 토크나이징)
```

### 검색 플로우

#### 표 검색
```
쿼리 → SentenceTransformer 임베딩 → ChromaDB similarity search → 결과 반환
(선택: Smart Search → 상위 20개 후보 → LLM이 최적 표 1개 선택)
```

#### 텍스트 검색 (Document QA)
```
쿼리 → SentenceTransformer 임베딩 → ChromaDB 검색 (k=8)
     → BM25 키워드 검색 (k=8)
     → RRF Fusion (Reciprocal Rank Fusion)
     → 상위 5개 청크 → LLM에 컨텍스트로 전달
     → SSE 스트리밍으로 답변 생성 + 출처 페이지 반환
```

---

## 화면 구성

### 탭 구조

| 탭 | 설명 |
|---|---|
| **메인** | PDF 업로드, 전체 문서 현황 대시보드 |
| **문서 보기** | PDF 페이지 뷰어 + 테이블 오버레이 + 하이라이트 |
| **표 검색** | 표 의미 검색 + Smart Search + 표별 Q&A |
| **텍스트 검색** | 문서 전체 기반 자연어 QA + 출처 하이라이트 |
| **기업금융심사** | 문서 내 이미지/차트 분석 뷰 |

### UI 레이아웃

```
┌──────────┬───────────────────────────────────────────────────┐
│          │  [탭 바: 메인 | 문서보기 | 표검색 | 텍스트검색 | 심사] │
│          ├───────────────────────────────────────────────────┤
│ 사이드바 │                                                   │
│          │                                                   │
│ • 세션명  │              메인 콘텐츠 영역                      │
│ • PDF목록 │                                                   │
│ • 업로드  │                                                   │
│ • 세션관리 │                                                   │
│          │                                                   │
│ • 초기화  │                                                   │
│          │                                                   │
└──────────┴───────────────────────────────────────────────────┘
```

---

## 빠른 시작

### 사전 요구사항

- Python 3.11 이상
- Node.js 18 이상
- npm 9 이상

### 5분 만에 실행하기

```bash
# 1. 저장소 클론
git clone https://github.com/hong0814/pdf-intelligence-portal.git
cd pdf-intelligence-portal

# 2. Python 가상환경 설정
python -m venv .venv
source .venv/bin/activate

# 3. Python 패키지 설치
pip install -e .

# 4. 하이브리드 변환 서버 시작 (OCR 지원)
opendataloader-pdf-hybrid --port 5002 &

# 5. 환경 변수 설정 (.env 파일)
echo 'ZAI_API_KEY=your_api_key_here' > .env

# 6. 프론트엔드 빌드
cd web
npm install
npm run build
cd ..

# 7. 서버 실행
uvicorn pdftablesearch.web_server:app --reload --port 8000

# 8. 브라우저에서 접속
open http://localhost:8000
```

---

## 상세 실행 방법

### 1. 백엔드 설정

#### 환경 변수

`.env` 파일을 프로젝트 루트에 생성:

```bash
ZAI_API_KEY=your_z_ai_api_key_here
```

#### 하이브리드 변환 서버

OCR 기반의 고품질 PDF 변환을 위해 `docling-fast` 서버를 실행해야 합니다:

```bash
# 서버 시작 (백그라운드)
opendataloader-pdf-hybrid --port 5002 &

# 상태 확인
curl http://localhost:5002/health
```

> 하이브리드 서버가 없으면 표준 변환 모드로 자동 폴백(fallback)됩니다. 표 인식률이 떨어질 수 있습니다.

#### FastAPI 서버 실행

```bash
# 개발 모드 (자동 리로드)
uvicorn pdftablesearch.web_server:app --reload --port 8000

# 프로덕션 모드
uvicorn pdftablesearch.web_server:app --host 0.0.0.0 --port 8000
```

서버가 시작되면 `http://localhost:8000/api/health` 에서 상태를 확인할 수 있습니다.

### 2. 프론트엔드 설정

```bash
cd web

# 의존성 설치
npm install

# 개발 서버 (HMR 지원)
npm run dev

# 프로덕션 빌드
npm run build

# 빌드 미리보기
npm run preview
```

개발 모드(`npm run dev`)는 기본적으로 `http://localhost:5173`에서 실행되며, API 요청을 `localhost:8000`으로 프록시합니다.

### 3. 전체 실행 (한 번에)

```bash
# 터미널 1: 하이브리드 서버
opendataloader-pdf-hybrid --port 5002

# 터미널 2: FastAPI 백엔드
uvicorn pdftablesearch.web_server:app --reload --port 8000

# 터미널 3: React 개발 서버 (선택)
cd web && npm run dev
```

---

## 프로젝트 구조

```
pdftablesearch/
├── pdftablesearch/          # Python 백엔드 패키지
│   ├── __init__.py          # 패키지 초기화, 퍼블릭 API
│   ├── web_server.py        # FastAPI 웹 서버 (세션 관리, API 라우트)
│   ├── core.py              # 코어 검색 로직
│   ├── search.py            # 검색 인터페이스
│   ├── smart_search.py      # Smart Search (LLM 표 선택)
│   ├── table_qa.py          # 표 기반 질의응답
│   ├── vectorstore.py       # ChromaDB 벡터 저장소 래퍼
│   ├── embedding_provider.py # 임베딩 제공자 인터페이스
│   ├── local_embeddings.py  # 로컬 SentenceTransformer 임베딩
│   ├── embeddings.py        # z.ai API 임베딩
│   ├── llm_client.py        # z.ai LLM 클라이언트
│   ├── hybrid_search.py     # 하이브리드 검색
│   ├── reranker.py          # LLM 리랭킹
│   ├── translation.py       # 문서 번역
│   ├── config.py            # 설정 관리
│   ├── models.py            # 데이터 모델
│   ├── exceptions.py        # 커스텀 예외
│   ├── utils.py             # 유틸리티
│   └── loader/              # PDF 로딩 및 테이블 추출
│       ├── __init__.py      # PDFProcessor
│       ├── html_parser.py   # HTML 테이블 추출, Markdown 변환
│       ├── json_parser.py   # JSON 메타데이터 파싱
│       ├── markdown_parser.py # Markdown 테이블 파싱
│       └── matcher.py       # HTML↔JSON 매칭
│
├── web/                     # React 프론트엔드
│   ├── src/
│   │   ├── App.tsx          # 메인 앱 컴포넌트
│   │   ├── main.tsx         # 진입점
│   │   ├── api/
│   │   │   └── client.ts    # API 클라이언트 함수
│   │   ├── store/
│   │   │   └── useAppStore.ts # Zustand 상태 관리
│   │   ├── types/
│   │   │   └── index.ts     # TypeScript 타입 정의
│   │   └── components/
│   │       ├── SearchBar.tsx       # 검색 입력창 (PDF 선택 필터)
│   │       ├── SearchResults.tsx   # 표 검색 결과 목록
│   │       ├── TableCard.tsx       # 개별 표 카드 (Q&A 포함)
│   │       ├── QAPanel.tsx         # 텍스트 검색 (문서 QA)
│   │       ├── ChatBubble.tsx      # QA 메시지 버블 + 출처 하이라이트
│   │       ├── DocumentViewer.tsx  # PDF 페이지 뷰어 (pdf.js)
│   │       ├── CreditReviewView.tsx # 기업금융심사 (이미지 분석)
│   │       ├── Sidebar.tsx         # 사이드바 (PDF 목록, 업로드)
│   │       ├── TabBar.tsx          # 탭 네비게이션
│   │       ├── SessionHeader.tsx   # 세션 헤더
│   │       ├── MainScreen.tsx      # 메인 대시보드
│   │       └── ProgressBar.tsx     # 진행 상태 표시
│   ├── vite.config.ts       # Vite 설정 (프록시 등)
│   ├── package.json         # npm 의존성
│   └── tailwind.config.js   # Tailwind CSS 설정
│
├── tests/                   # Python 테스트
├── docs/                    # 문서
├── examples/                # 사용 예제
├── pyproject.toml           # Python 프로젝트 설정
├── .env.example             # 환경 변수 예제
├── requirements-web.txt     # 웹 의존성
└── run_web_demo.sh          # Streamlit 데모 실행 스크립트 (deprecated)
```

---

## 기술 스택

| 계층 | 기술 | 버전 |
|------|------|------|
| **프론트엔드** | React + TypeScript | 19.x |
| | Vite | 8.x |
| | Tailwind CSS | 4.x |
| | Zustand (상태 관리) | 5.x |
| | react-markdown + remark-gfm | 10.x / 4.x |
| | pdf.js (CDN) | 4.0 |
| **백엔드** | FastAPI | 0.100+ |
| | Uvicorn (ASGI) | 0.20+ |
| **PDF 처리** | opendataloader-pdf (hybrid) | 2.2+ |
| | docling-fast (OCR) | - |
| | PyMuPDF (fitz) | 1.24+ |
| | BeautifulSoup4 | 4.12+ |
| **임베딩** | SentenceTransformers (bge-m3) | 2.0+ |
| | z.ai Embedding API | embedding-3 |
| **벡터 DB** | ChromaDB | 0.4+ |
| **LLM** | z.ai API (ChatOpenAI 호환) | glm-4.7 |
| **검색** | BM25Okapi (rank-bm25) | 0.2+ |
| | LangChain | 0.1+ |
| **데이터** | Pandas | 2.0+ |

---

## 트러블슈팅

### 문제: 하이브리드 서버 연결 실패

```bash
# 서버 상태 확인
curl http://localhost:5002/health

# 서버가 없으면 시작
opendataloader-pdf-hybrid --port 5002 &
```

하이브리드 서버가 없으면 표준 변환 모드로 자동 폴백됩니다. 표 인식률이 떨어질 수 있으니 가능하면 실행하세요.

### 문제: z.ai API 429 Rate Limit

`glm-4.7` 모델 사용 시에도 z.ai 서버 과부하로 429 에러가 발생할 수 있습니다.

- 잠시 기다렸다가 재시도 (서버에서 자동으로 최대 5회, 15초~75초 간격으로 재시도)
- `.env`에서 `ZAI_API_KEY`가 올바른지 확인

### 문제: PDF 업로드 실패 (ChromaDB readonly)

upload 중 "attempt to write a readonly database" 에러가 발생하면:

- `vectorstore.py`가 자동으로 디렉토리를 재생성하여 재시도 (최대 2회)
- 서버를 재시작하여 `/tmp` 내 임시 파일 정리

### 문제: 페이지 번호와 내용 불일치

문서 청킹이 페이지 구분자(`<div class='page-sep' data-pn='N'>`)를 기준으로 수행되므로, 출처 페이지 번호는 실제 페이지와 일치해야 합니다. 불일치가 발생하면 문서를 다시 업로드하세요.

---

## 라이선스

이 프로젝트는 Apache License 2.0 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 확인하세요.
