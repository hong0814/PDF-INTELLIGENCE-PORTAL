# PDF Intelligence Portal

PDF 문서에서 표와 텍스트를 통합 검색하고, AI 기반 질의응답을 통해 문서를 분석하는 웹 애플리케이션입니다.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![LangChain](https://img.shields.io/badge/langchain-0.1.0-green.svg)](https://github.com/langchain-ai/langchain)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-0.4.0-orange.svg)](https://www.trychroma.com/)
[![Ollama](https://img.shields.io/badge/Ollama-gpt--oss:120b-purple.svg)](https://ollama.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

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
| **통합 문서 검색** | 표와 텍스트를 동시에 검색하여 하나의 AI 답변으로 종합 |
| **의미적 검색** | 단순 키워드 매칭이 아닌 문맥을 이해하고 검색 |
| **출처 팝업** | 답변의 출처를 클릭하면 실제 PDF 페이지를 렌더링하여 해당 텍스트를 하이라이트 |
| **후속 질문** | 검색 결과에 대해 추가 질문을 통해 심층 분석 가능 |
| **다중 문서 지원** | 여러 PDF를 동시에 업로드하고 선택적으로 검색 |
| **한국어 완벽 지원** | 한국어 질문과 문서를 완벽하게 처리 |
| **세션 관리** | 여러 세션을 생성하고 전환하며 독립적인 작업 환경 유지 |

---

## 주요 기능

### 1. 문서 검색 (Unified Search)

표와 텍스트를 **동시에 검색**하여 AI가 종합적인 답변을 생성합니다. ChromaDB 벡터 검색 + BM25 키워드 검색을 RRF(Rank Reciprocal Fusion)로 결합하여 높은 정확도를 달성합니다.

- **하이브리드 검색**: 벡터 유사도 검색 + BM25 키워드 검색 → RRF Fusion
- **AI 답변**: LLM이 관련 표와 텍스트를 종합하여 한국어 답변 생성 (SSE 스트리밍)
- **출처 인용**: `[텍스트출처N]`, `[표출처N]` 마커로 답변 근거를 명확히 표시
- **출처 팝업**: 출처 클릭 시 실제 PDF 페이지를 렌더링하고 매칭된 텍스트를 하이라이트 (6단계 폴백 매칭)
- **관련 표**: 답변과 관련된 표를 인라인으로 렌더링, CSV 다운로드 지원
- **후속 질문**: 이전 검색 컨텍스트를 유지한 채 추가 질문 가능

### 2. 문서 보기 (Document Viewer)

업로드된 PDF를 페이지 단위로 열람할 수 있습니다. pdf.js를 사용한 고화질 렌더링과 함께, 추출된 표의 위치를 오버레이로 표시합니다.

- PyMuPDF + opendataloader-pdf 이중 감지로 높은 표 인식률
- 동적 페이지 크기 적용 (A4 외 다양한 페이지 크기 지원)
- Hybrid bbox 우선 사용으로 정확한 표 경계 표시
- 표 클릭 시 CSV 다운로드

### 3. 표 검색 (Table Search)

PDF 문서에서 추출된 표를 의미적으로 검색합니다. ChromaDB 벡터 데이터베이스와 로컬 임베딩 모델을 사용하여 관련성 높은 표를 찾아줍니다.

**Smart Search 모드**: 검색된 여러 표 중 AI(LLM)가 가장 관련성 높은 표 하나를 자동으로 선택해 보여줍니다.

### 4. 기업금융심사 (Credit Review)

PDF에서 추출된 이미지(차트, 도표 등)를 주변 텍스트 컨텍스트와 함께 확인할 수 있는 특화 뷰입니다. 금융 문서의 시각적 데이터를 효율적으로 검토할 수 있습니다.

### 5. 세션 관리

- **세션 생성/전환/삭제**: 여러 독립적인 작업 환경을 관리
- **검색 기록 유지**: 세션을 전환해도 각 세션의 검색 결과와 대화 기록이 localStorage에 보존
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
│  │ Main     │ │ Document │ │ Unified  │ │ Credit   │           │
│  │ Screen   │ │ Viewer   │ │ Search   │ │ Review   │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│                                                                  │
│  State Management: Zustand (useAppStore)                        │
│  Styling: Tailwind CSS v4                                       │
│  Markdown: react-markdown + remark-gfm + rehype-raw             │
│  PDF Rendering: pdf.js 4.0 (CDN)                                │
└──────────────────────────────────────────────────────────────────┘
                                │ HTTP/SSE
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                  FastAPI Backend (Python 3.11)                   │
│                                                                  │
│  POST /api/upload            - PDF 업로드 & 테이블 추출          │
│  POST /api/search            - 표 검색 (벡터 유사도)             │
│  POST /api/smart-search      - AI 표 선택 검색 (SSE)            │
│  POST /api/unified-search    - 통합 문서 검색 (SSE)              │
│  POST /api/unified-followup  - 후속 질문 (SSE)                  │
│  POST /api/ask-document      - 문서 QA (RAG + LLM, SSE)         │
│  POST /api/qa                - 표 Q&A (SSE)                     │
│  GET/POST/DELETE /api/sessions - 세션 관리                       │
│  GET  /api/documents/*       - PDF/HTML/이미지 서빙              │
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
│ Hybrid Mode:      │ │                    │ │ pdf_tables        │
│ docling-fast       │ │                    │ │ doc_chunks        │
│ (OCR 기반)        │ │                    │ │                   │
└───────────────────┘ └───────────────────┘ └───────────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  PyMuPDF (fitz)   │ │  Ollama Cloud     │ │   BM25 Index       │
│  표 감지 + bbox    │ │  gpt-oss:120b     │ │   (키워드 검색)    │
│  동적 페이지 크기   │ │  (LLM 응답 생성)  │ │                   │
└───────────────────┘ └───────────────────┘ └───────────────────┘
```

### 데이터 처리 파이프라인

```
PDF 업로드
  → opendataloader-pdf 변환 (hybrid=docling-fast, OCR 지원)
  → HTML 파일 생성 (페이지 구분자 포함)
  → HTML에서 <table> 태그 추출 (BeautifulSoup)
  → JSON 메타데이터 매칭 (페이지 번호, bounding box)
  → PyMuPDF 표 감지 (find_tables) + hybrid 표 매칭
    → PyMuPDF가 감지한 표 → hybrid HTML 매칭 → bbox는 hybrid 우선 사용
    → PyMuPDF가 놓친 페이지 → hybrid 표를 fallback으로 복구
  → 다중페이지 표 연결 감지 (chain detection)
  → LangChain Document 생성 (table_html + metadata)
  → SentenceTransformer 임베딩 (bge-m3, 로컬 CPU)
  → ChromaDB 저장 (pdf_tables + doc_chunks 컬렉션)

문서 청킹 (텍스트 검색용)
  → HTML에서 표 제거 + 페이지 구분자로 분할
  → RecursiveCharacterTextSplitter (1000자 청크)
  → ChromaDB 저장 (doc_chunks 컬렉션)
  → BM25 인덱스 생성 (한국어 토크나이징)
```

### 검색 플로우

#### 통합 문서 검색 (Unified Search)
```
쿼리 → ChromaDB pdf_tables 검색 (k=10)     ─┐
     → ChromaDB doc_chunks 검색 (k=10)      ─┤
     → BM25 키워드 검색 (k=10)              ─┤
                                                ├→ RRF Fusion
     ← 상위 표/텍스트 결과 병합             ─┤
                                                │
     → LLM에 컨텍스트 전달 (gpt-oss:120b)   ─┘
     → SSE 스트리밍으로 AI 답변 생성
     → 출처 정보 + 관련 표 + 원본 텍스트 반환
```

#### 표 검색
```
쿼리 → SentenceTransformer 임베딩 → ChromaDB similarity search → 결과 반환
(선택: Smart Search → 상위 20개 후보 → LLM이 최적 표 1개 선택)
```

---

## 화면 구성

### 탭 구조

| 탭 | 설명 |
|---|---|
| **메인** | PDF 업로드, 전체 문서 현황 대시보드 (문서 보기 / 문서 검색 카드) |
| **문서 보기** | PDF 페이지 뷰어 + 테이블 오버레이 + 하이라이트 + CSV 다운로드 |
| **문서 검색** | 표+텍스트 통합 검색 + AI 답변 + 출처 팝업 + 후속 질문 |
| **기업금융심사** | 문서 내 이미지/차트 분석 뷰 |

### UI 레이아웃

```
┌──────────┬───────────────────────────────────────────────────┐
│          │  [탭 바: 메인 | 문서보기 | 문서검색 | 심사]        │
│          ├───────────────────────────────────────────────────┤
│ 사이드바 │                                                   │
│          │  ┌─ 문서 검색 탭 ──────────────────────────────┐  │
│ • 세션명  │  │ 🔍 검색바 (PDF 필터 칩)                      │  │
│ • PDF목록 │  │                                              │  │
│ • 업로드  │  │ 📋 AI 답변 카드                              │  │
│ • 세션관리 │  │   • 마크다운 렌더링 (표/볼드/리스트)           │  │
│          │  │   • [텍스트출처N] [표출처N] 인라인 칩          │  │
│ • 초기화  │  │   • 관련 표 (펼치기/접기 + CSV 다운로드)      │  │
│          │  │   • 출처 칩 (클릭 → PDF 팝업)                 │  │
│          │  │                                              │  │
│          │  │ 💬 후속 질문 입력바                            │  │
│          │  └──────────────────────────────────────────────┘  │
└──────────┴───────────────────────────────────────────────────┘
```

---

## 빠른 시작

### 사전 요구사항

- Python 3.11 이상
- `uv` (`brew install uv` 또는 공식 설치 방법)
- Homebrew OpenLDAP (`brew install openldap`) - 로컬 개발용 LDAP 서버 실행 시 필요
- Node.js 18 이상 / npm 9 이상 - 웹 프론트 빌드 또는 `npm run dev` 사용 시 필요
- `.env.example`에 맞는 LLM API 설정값 (예: `ZAI_API_KEY`)

### 5분 만에 실행하기

```bash
# 1. 저장소 클론
git clone https://github.com/hong0814/PDF-INTELLIGENCE-PORTAL.git
cd PDF-INTELLIGENCE-PORTAL

# 2. Python 의존성 설치 (권장)
uv sync

# 참고: 별도 sync 없이도 `uv run <command>`로 필요한 의존성을 해석하며 실행할 수 있습니다.

# 3. 환경 변수 파일 생성
cp .env.example .env

# 4. 로컬 개발용 LDAP 서버 준비
brew install openldap
uv run ldap

# 5. 하이브리드 변환 서버 시작 (OCR 지원)
uv run opendataloader-pdf-hybrid --port 5002 &

# 6. 프론트엔드 빌드 (FastAPI가 정적 파일 서빙)
cd web
npm install
npm run build
cd ..

# 7. 백엔드 실행
uv run uvicorn pdftablesearch.web_server:app --reload --port 8000

# 8. 브라우저에서 접속
open http://localhost:8000
```

`.env`는 `.env.example`을 복사한 뒤 필요한 값만 수정하면 됩니다. 로컬 LDAP/JWT 개발 기본값은 이미 포함되어 있으므로 보통 `ZAI_API_KEY` 등 현재 사용하는 API 값만 채우면 됩니다.

앱에 접속하면 먼저 LDAP 로그인 화면이 표시되며, 로그인 후 사용자별 세션을 생성해서 작업합니다. 개발용 seeded 계정은 `123456 / 1234`, `admin / admin`입니다.

현재 PDF portal의 LDAP/JWT 인증 흐름에는 Redis가 필요하지 않습니다. 이 LDAP 서버는 로컬 개발 전용이며 `ldap://` plaintext 연결만 사용합니다. TLS는 설정되어 있지 않으므로 운영 환경에서 사용하면 안 되며, seeded 계정/예시 비밀번호/예시 JWT secret도 운영 환경에서 사용하면 안 됩니다. LDAP 서버 종료는 `uv run ldap-stop`으로 할 수 있습니다.

---

## 상세 실행 방법

### 1. 백엔드 설정

#### 환경 변수

프로젝트 루트에서 `.env.example`를 복사해 `.env`를 만듭니다:

```bash
cp .env.example .env
```

로컬 LDAP/JWT 로그인 기준으로 먼저 확인할 값은 아래와 같습니다.

- `ZAI_API_KEY`: 현재 사용하는 LLM/embedding API 키
- `LDAP_SERVER_URL=ldap://localhost:3890`
- `LDAP_USE_TLS=false`
- `LDAP_BASE_DN=OU=YourCompany,DC=hc,DC=com`
- `LDAP_SERVICE_BIND_DN=CN=admin,DC=hc,DC=com`
- `LDAP_SERVICE_BIND_PASSWORD=secret`
- `AUTH_SECRET_KEY=replace-with-a-strong-random-secret`

`.env.example`에는 로컬 LDAP 개발 기본값과 JWT 쿠키 예시값이 이미 들어 있습니다. 로컬 개발에서는 그대로 써도 되지만, 운영 환경에서는 `AUTH_SECRET_KEY`를 강한 랜덤 값으로 교체하고 `AUTH_COOKIE_SECURE=true`를 사용하세요.

> 임베딩은 로컬 `BAAI/bge-m3` 모델을 사용하므로 임베딩용 별도 API 키가 필요하지 않습니다.

#### 로컬 개발용 LDAP 서버

현재 PDF portal 인증은 LDAP bind + JWT 쿠키만 사용합니다. `analytics_agent`와 달리 이 로컬 LDAP 서버 시작/정지나 현재 인증 흐름에는 Redis가 필요하지 않습니다.
이 서버는 로컬 개발 전용이며 `ldap://` plaintext 연결만 제공합니다. TLS는 지원하지 않으므로 운영 환경에 사용하면 안 됩니다.

```bash
# OpenLDAP 도구 설치
brew install openldap

# 로컬 LDAP 서버 시작
uv run ldap

# 서버 종료
uv run ldap-stop
```

`.env.example`의 LDAP 기본값은 위 로컬 서버 seed 데이터와 맞춰져 있습니다. `LDAP_PORT`나 `LDAP_RUN_DIR`를 바꿔 실행했다면 `.env`의 `LDAP_SERVER_URL`도 함께 맞추세요.

기본 runtime 디렉터리는 포트별로 분리되며 `LDAP_PORT=3891`이면 `/tmp/pdf-intelligence-portal-ldap-3891`을 사용합니다. 필요하면 `LDAP_RUN_DIR`로 명시적으로 덮어쓸 수 있습니다.

기본값은 다음과 같습니다.

- LDAP URL: `ldap://localhost:3890`
- Root DN: `CN=admin,DC=hc,DC=com`
- Root password: `secret`
- Base DN: `OU=YourCompany,DC=hc,DC=com`
- Seeded users: `123456 / 1234`, `admin / admin`

운영 환경에서는 seeded 계정과 예시 비밀번호를 절대 사용하지 마세요.

#### LLM 모델 변경

Ollama 클라우드에서 제공하는 다양한 모델을 사용할 수 있습니다:

```bash
# 사용 가능한 모델 목록 확인
curl -s https://ollama.com/api/tags \
  -H "Authorization: Bearer $ZAI_API_KEY" | python3 -m json.tool
```

| 모델 | 크기 | 특징 |
|------|------|------|
| `gpt-oss:120b` | 65GB | 기본 모델, 사고( reasoning) 지원 |
| `gemma4:31b` | 62GB | Google Gemma 4, 빠른 응답 |
| `qwen3.5:397b` | 397GB | 최대급, 최고 품질 |
| `deepseek-v4-flash` | 140GB | 빠른 추론 |

모델 변경 시 `.env`에서 `ZAI_LLM_MODEL` 값을 수정하세요.

#### 하이브리드 변환 서버

OCR 기반의 고품질 PDF 변환을 위해 `docling-fast` 서버를 실행해야 합니다:

```bash
# 서버 시작 (백그라운드)
uv run opendataloader-pdf-hybrid --port 5002 &

# 상태 확인
curl http://localhost:5002/health
```

> 하이브리드 서버가 없으면 표준 변환 모드로 자동 폴백(fallback)됩니다. 표 인식률이 떨어질 수 있습니다.

#### FastAPI 서버 실행

```bash
# 개발 모드 (자동 리로드)
uv run uvicorn pdftablesearch.web_server:app --reload --port 8000

# 프로덕션 모드
uv run uvicorn pdftablesearch.web_server:app --host 0.0.0.0 --port 8000
```

서버가 시작되면 `http://localhost:8000/api/health`에서 상태를 확인할 수 있습니다. `web/dist`가 있으면 FastAPI가 `http://localhost:8000/`에서 프론트엔드 정적 파일도 함께 서빙합니다.

### 2. 프론트엔드 설정

웹 프론트엔드를 수정하거나 새로 빌드할 때만 Node/npm이 필요합니다.

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

개발 모드(`npm run dev`)는 기본적으로 `http://localhost:5173`에서 실행되며, API 요청을 `localhost:8000`으로 프록시합니다. `npm run build` 결과물은 `web/dist`에 생성되고, 이후 FastAPI가 이를 정적으로 서빙합니다.

### 3. 전체 실행 (한 번에)

```bash
# 터미널 1: 로컬 개발용 LDAP 서버
uv run ldap

# 터미널 2: 하이브리드 서버
uv run opendataloader-pdf-hybrid --port 5002

# 터미널 3: FastAPI 백엔드
uv run uvicorn pdftablesearch.web_server:app --reload --port 8000

# 터미널 4: React 개발 서버 (선택)
cd web && npm run dev
```

로컬 로그인 테스트는 `123456 / 1234` 또는 `admin / admin`으로 할 수 있습니다. 이 조합은 개발 전용이며 Redis 없이 동작합니다.

---

## 프로젝트 구조

```
pdftablesearch/
├── pdftablesearch/          # Python 백엔드 패키지
│   ├── __init__.py          # 패키지 초기화, 퍼블릭 API
│   ├── web_server.py        # FastAPI 웹 서버 (API 라우트, 통합 검색)
│   ├── core.py              # 코어 검색 로직
│   ├── search.py            # 검색 인터페이스
│   ├── smart_search.py      # Smart Search (LLM 표 선택)
│   ├── table_qa.py          # 표 기반 질의응답
│   ├── vectorstore.py       # ChromaDB 벡터 저장소 래퍼
│   ├── embedding_provider.py # 임베딩 제공자 인터페이스
│   ├── local_embeddings.py  # 로컬 SentenceTransformer 임베딩
│   ├── embeddings.py        # API 임베딩 (fallback)
│   ├── llm_client.py        # Ollama LLM 클라이언트 (ChatOpenAI 호환)
│   ├── hybrid_search.py     # 하이브리드 검색 (벡터 + BM25 + RRF)
│   ├── reranker.py          # LLM 리랭킹
│   ├── translation.py       # 문서 번역
│   ├── config.py            # 설정 관리 (Ollama API 키, 모델)
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
│   │   │   └── client.ts    # API 클라이언트 (SSE 스트리밍 포함)
│   │   ├── store/
│   │   │   └── useAppStore.ts # Zustand 상태 관리
│   │   ├── types/
│   │   │   └── index.ts     # TypeScript 타입 정의
│   │   └── components/
│   │       ├── UnifiedSearchView.tsx # 통합 문서 검색 (AI 답변 + 출처 팝업)
│   │       ├── DocumentViewer.tsx    # PDF 페이지 뷰어 (pdf.js + 표 오버레이)
│   │       ├── SearchBar.tsx         # 검색 입력창 (PDF 선택 필터)
│   │       ├── SearchResults.tsx     # 표 검색 결과 목록
│   │       ├── TableCard.tsx         # 개별 표 카드 (Q&A, CSV/HTML 다운로드)
│   │       ├── ChatBubble.tsx        # QA 메시지 버블 + 출처 하이라이트
│   │       ├── CreditReviewView.tsx  # 기업금융심사 (이미지 분석)
│   │       ├── Sidebar.tsx           # 사이드바 (PDF 목록, 업로드)
│   │       ├── TabBar.tsx            # 탭 네비게이션
│   │       ├── MainScreen.tsx        # 메인 대시보드
│   │       └── ProgressBar.tsx       # 진행 상태 표시
│   ├── vite.config.ts       # Vite 설정 (프록시 등)
│   └── package.json         # npm 의존성
│
├── tests/                   # Python 테스트
├── docs/                    # 문서
├── pyproject.toml           # Python 프로젝트 설정
└── .env                     # 환경 변수 (gitignore)
```

---

## 기술 스택

| 계층 | 기술 | 버전 |
|------|------|------|
| **프론트엔드** | React + TypeScript | 19.x |
| | Vite | 8.x |
| | Tailwind CSS | 4.x |
| | Zustand (상태 관리) | 5.x |
| | react-markdown + remark-gfm + rehype-raw | 10.x / 4.x / 7.x |
| | pdf.js (CDN) | 4.0 |
| **백엔드** | FastAPI | 0.100+ |
| | Uvicorn (ASGI) | 0.20+ |
| | LangChain | 0.1+ |
| **PDF 처리** | opendataloader-pdf (hybrid) | 2.2+ |
| | PyMuPDF (fitz) | 1.24+ |
| | BeautifulSoup4 | 4.12+ |
| **임베딩** | SentenceTransformers (bge-m3) | 2.0+ |
| **벡터 DB** | ChromaDB | 0.4+ |
| **LLM** | Ollama Cloud (gpt-oss:120b) | - |
| **검색** | BM25Okapi (rank-bm25) | 0.2+ |
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

하이브리드 서버가 없으면 표준 변환 모드로 자동 폴백됩니다。표 인식률이 떨어질 수 있으니 가능하면 실행하세요。

### 문제: Ollama API 오류

```bash
# API 연결 테스트
curl https://ollama.com/v1/chat/completions \
  -H "Authorization: Bearer $ZAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-oss:120b","messages":[{"role":"user","content":"test"}],"max_tokens":10}'
```

- `.env`에서 `ZAI_API_KEY`가 올바른지 확인
- `ZAI_LLM_MODEL`이 Ollama에서 지원하는 모델명인지 확인

### 문제: 특정 페이지에서 표가 감지되지 않음

PyMuPDF의 `find_tables()`가 표를 감지하지 못하는 경우가 있습니다 (셀 병합, 테두리 없는 표 등). 이 경우 hybrid 파이프라인(opendataloader-pdf)에서 감지한 표가 자동으로 fallback으로 포함됩니다.

서버 로그에서 `[build] fallback` 메시지로 확인할 수 있습니다.

### 문제: PDF 업로드 실패 (ChromaDB readonly)

upload 중 "attempt to write a readonly database" 에러가 발생하면:

- `vectorstore.py`가 자동으로 디렉토리를 재생성하여 재시도 (최대 2회)
- 서버를 재시작하여 `/tmp` 내 임시 파일 정리

### 문제: 페이지 번호와 내용 불일치

문서 청킹이 페이지 구분자(`<div class='page-sep' data-pn='N'>`)를 기준으로 수행되므로, 출처 페이지 번호는 실제 페이지와 일치해야 합니다. 불일치가 발생하면 문서를 다시 업로드하세요。

---

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다。자세한 내용은 [LICENSE](LICENSE) 파일을 확인하세요。
