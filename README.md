# PDF Intelligence Portal

PDF 문서에서 표와 텍스트를 통합 검색하고, AI 기반 질의응답을 통해 문서를 분석하는 웹 애플리케이션입니다.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![LangChain](https://img.shields.io/badge/langchain-0.1.0-green.svg)](https://github.com/langchain-ai/langchain)
[![Weaviate](https://img.shields.io/badge/Weaviate-local%20embedded-yellow.svg)](https://weaviate.io/)
[![Ollama](https://img.shields.io/badge/Ollama-gpt--oss:120b-purple.svg)](https://ollama.com/)
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

PDF 문서에서 추출된 표를 의미적으로 검색합니다. Weaviate 또는 ChromaDB 벡터 데이터베이스와 로컬 임베딩 모델을 사용하여 관련성 높은 표를 찾아줍니다.

**Smart Search 모드**: 검색된 여러 표 중 AI(LLM)가 가장 관련성 높은 표 하나를 자동으로 선택해 보여줍니다.

### 4. 기업금융심사 (Credit Review)

PDF에서 추출된 이미지(차트, 도표 등)를 주변 텍스트 컨텍스트와 함께 확인할 수 있는 특화 뷰입니다. 금융 문서의 시각적 데이터를 효율적으로 검토할 수 있습니다.

### 5. 세션 관리

- **세션 생성/전환/삭제**: 여러 독립적인 작업 환경을 관리
- **검색 기록 유지**: 세션을 전환해도 각 세션의 검색 결과와 대화 기록이 localStorage에 보존
- **PDF 선택 필터링**: 여러 PDF 중 원하는 문서만 선택하여 검색 범위 제한

### 6. 로그인 및 idle timeout

- **LDAP-compatible 로그인 API**: UI가 `/api/auth/ldap`로 로그인하고 API가 httpOnly 세션 쿠키를 발급
- **로컬 개발 계정**: LDAP 서버가 없으면 `admin/admin`, `123456/1234` dev user로 로그인
- **10분 idle logout**: 브라우저 입력이 없으면 경고 후 `/api/auth/logout`을 호출하고 로그인 화면으로 복귀
- **서버 강제 idle timeout**: FastAPI middleware가 API 요청마다 마지막 활동 시간을 검사해 10분 초과 세션을 차단

---

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│                        사용자 (Browser)                          │
│                  http://localhost:8110                           │
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
│ opendataloader-pdf│ │ SentenceTransformers│ │ Weaviate/Chroma   │
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
  → Vector backend 저장 (Weaviate 기본, Chroma fallback)

문서 청킹 (텍스트 검색용)
  → HTML에서 표 제거 + 페이지 구분자로 분할
  → RecursiveCharacterTextSplitter (1000자 청크)
  → Vector backend 저장 (doc_chunks 논리 컬렉션)
  → BM25 인덱스 생성 (한국어 토크나이징)
```

### 검색 플로우

#### 통합 문서 검색 (Unified Search)
```
쿼리 → vector pdf_tables 검색 (k=10)       ─┐
     → vector doc_chunks 검색 (k=10)        ─┤
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
쿼리 → SentenceTransformer 임베딩 → vector similarity search → 결과 반환
(선택: Smart Search → 상위 20개 후보 → LLM이 최적 표 1개 선택)
```

#### 텍스트 검색 (Document QA)
```
쿼리 → SentenceTransformer 임베딩 → vector 검색 (k=8)
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
- Node.js 18 이상
- npm 9 이상
- Ollama API 키 ([ollama.com](https://ollama.com) 가입)

### 5분 만에 실행하기

```bash
# 1. 저장소 클론
git clone https://github.com/hong0814/PDF-INTELLIGENCE-PORTAL.git
cd PDF-INTELLIGENCE-PORTAL

# 2. Python workspace/Node 의존성 설치 및 React 빌드
uv sync --all-packages --extra dev
uv run ui-build

# 3. 환경 변수 설정
cp .env.example .env

# 4. Weaviate 백엔드로 전체 서비스 실행
uv run all
open http://localhost:8110
```

> 현재 기본 벡터 backend는 Weaviate입니다. ChromaDB adapter는 rollback/fallback 용도로 남겨두었고, 필요할 때만 `VECTOR_BACKEND=chroma`로 전환합니다.

---

## 상세 실행 방법

### 1. 백엔드 설정

#### 환경 변수

`.env` 파일을 프로젝트 루트에 생성:

```bash
# Ollama LLM 설정
OLLAMA_API_KEY=your_ollama_api_key_here
ZAI_LLM_ENDPOINT=https://ollama.com/v1
ZAI_LLM_MODEL=gpt-oss:120b

# Vector backend 설정
VECTOR_BACKEND=weaviate
WEAVIATE_DATA_DIR=./db/weaviate
```

`VECTOR_BACKEND=chroma`로 바꾸면 기존 ChromaDB fallback 경로를 사용할 수 있습니다.

#### 로그인 / LDAP 설정

기본값은 로컬 개발용 로그인입니다. LDAP 서버를 지정하지 않으면 아래 계정이 동작합니다.

| ID | PW | 용도 |
|---|---|---|
| `admin` | `admin` | 관리자 dev user |
| `123456` | `1234` | 일반 dev user |

```bash
AUTH_ENABLED=true
AUTH_IDLE_TIMEOUT_SECONDS=600
AUTH_WARN_BEFORE_SECONDS=60
AUTH_SESSION_TTL_SECONDS=3600
AUTH_DEV_USERS=123456:1234:Developer User:user,admin:admin:Administrator:admin
```

LDAP를 붙일 때는 `.env`에 서버와 bind/search 설정을 넣습니다.

```bash
LDAP_SERVER=ldap://localhost:3890
LDAP_BASE_DN=DC=hc,DC=com
LDAP_BIND_DN=CN=admin,DC=hc,DC=com
LDAP_BIND_PASSWORD=secret
LDAP_USER_FILTER=(uid={username})
```

로그인 성공 시 API는 `pdf_portal_auth` httpOnly 쿠키와 `pdf_portal_auth_presence` marker 쿠키를 설정합니다. `/api/auth/config`가 idle timeout 값을 UI로 내려주고, React idle timer와 FastAPI middleware가 같은 600초 설정을 사용합니다. 로그인 후 화면 하단에는 남은 세션 시간이 `m:ss` 형식으로 표시되고, 마지막 60초에는 경고 모달에서 세션을 연장할 수 있습니다. 시간을 바꾸려면 `.env`의 `AUTH_IDLE_TIMEOUT_SECONDS`, `AUTH_WARN_BEFORE_SECONDS`, `AUTH_SESSION_TTL_SECONDS` 값을 조정합니다.

로그인 직후에는 PDF 처리 데이터 이용 안내 동의문이 표시됩니다. 동의문은 PDF 내용 추출, 표 CSV 다운로드, 번역 보조, 개인정보/민감정보 마스킹, 업로드 PDF 원본 7일 후 삭제 정책을 안내하며, 체크박스 동의 후에만 앱 화면으로 진입합니다.

#### Weaviate 설치 방식

이 프로젝트는 **embedded Weaviate**를 사용합니다. 별도 Docker 컨테이너나 시스템 전역 Weaviate 설치 없이, Python dependency와 로컬 데이터 디렉터리만으로 실행합니다.

설치 흐름:

```bash
# 1. uv workspace 전체 의존성 설치
uv sync --all-packages --extra dev

# 2. weaviate-client 설치 확인
uv run python -c "import weaviate; print(weaviate.__version__)"

# 3. embedded Weaviate background 실행
uv run qa start weaviate

# 4. readiness 확인
curl http://127.0.0.1:8113/v1/.well-known/ready
```

관련 설정:

| 설정 | 기본값 | 설명 |
|---|---|---|
| `VECTOR_BACKEND` | `weaviate` | API가 사용할 벡터 backend |
| `WEAVIATE_USE_EMBEDDED` | `true` | Python runner가 embedded Weaviate 실행 |
| `WEAVIATE_HOST` | `127.0.0.1` | Weaviate host |
| `WEAVIATE_PORT` | `8113` | Weaviate HTTP port |
| `WEAVIATE_GRPC_PORT` | `8114` | Weaviate gRPC port |
| `WEAVIATE_DATA_DIR` | `./db/weaviate` | 로컬 persistence 경로 |

처음 실행하면 `db/weaviate/` 아래에 Weaviate 데이터 파일이 생성됩니다. 이 데이터 파일들은 `.gitignore` 대상이고, 디렉터리 존재를 나타내는 `.gitkeep`만 추적합니다.

기존 `.env`를 이미 만들어 둔 경우 `VECTOR_BACKEND=chroma`가 남아 있을 수 있습니다. Weaviate로 실행하려면 `.env`를 다음처럼 맞춥니다.

```bash
VECTOR_BACKEND=weaviate
WEAVIATE_PORT=8113
WEAVIATE_GRPC_PORT=8114
WEAVIATE_DATA_DIR=./db/weaviate
```

> 임베딩은 로컬 `BAAI/bge-m3` 모델을 사용하므로 별도 API 키가 필요하지 않습니다.

#### LLM 모델 변경

Ollama 클라우드에서 제공하는 다양한 모델을 사용할 수 있습니다:

```bash
# 사용 가능한 모델 목록 확인
curl -s https://ollama.com/api/tags \
  -H "Authorization: Bearer $OLLAMA_API_KEY" | python3 -m json.tool
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
# 서버 시작
uv run qa start hybrid

# 상태 확인
curl http://localhost:8112/health
```

전체 로컬 스택이 필요하면 `uv run all` 또는 대화형 `uv run qa`에서 E2E QA를 선택하세요.

> 하이브리드 서버가 없으면 표준 변환 모드로 자동 폴백(fallback)됩니다. 표 인식률이 떨어질 수 있습니다.

#### FastAPI 서버 실행

```bash
# uv runner
uv run api start --port 8111

# backend package를 직접 지정해도 동일
uv run --package pdftablesearch api start --port 8111

# Weaviate backend로 실행하려면 먼저 Weaviate 실행
uv run qa start weaviate
uv run api start --port 8111
```

서버가 시작되면 `http://localhost:8111/api/health` 에서 상태를 확인할 수 있습니다.

#### Weaviate 백엔드 실행

Weaviate는 embedded local server로 실행되며 기본 포트와 저장 위치는 다음과 같습니다.

| 항목 | 기본값 |
|---|---|
| HTTP | `127.0.0.1:8113` |
| gRPC | `127.0.0.1:8114` |
| Data directory | `db/weaviate/` |
| Cluster hostname | `Embedded_at_50851` |
| Table collection | `PdfTable` |
| Chunk collection | `PdfChunk` |

```bash
# Weaviate만 foreground 실행
uv run weaviate

# 전체 서비스를 Weaviate backend로 실행
uv run all

# 상태 확인
uv run qa status
curl http://127.0.0.1:8113/v1/.well-known/ready
```

`db/weaviate/.gitkeep`만 git에 남기고 실제 Weaviate 데이터 파일은 `.gitignore`로 제외합니다.

### 2. 프론트엔드 설정

```bash
# 의존성 설치
uv run --package pdf-intelligence-web ui-build

# 개발 서버 (HMR 지원)
uv run ui

# 프로덕션 빌드
uv run ui-build

# 빌드 미리보기
uv run ui-preview
```

개발 모드(`uv run ui`)는 내부적으로 `web/package.json`의 `npm run dev`를 실행합니다. 기본적으로 `http://localhost:8110`에서 실행되며, API 요청을 `localhost:8111`으로 프록시합니다.

### 3. 전체 실행 (한 번에)

```bash
# 전체 서비스 시작 (Weaviate backend)
uv run all

# 대화형 QA 런처
uv run qa

# 상태 확인
uv run qa status

# 서비스 명령 확인
uv run qa commands

# 회귀 테스트
uv run qa test

# Weaviate 통합 테스트는 먼저 Weaviate를 background로 띄운 뒤 실행
uv run qa start weaviate
uv run qa test --weaviate

# 전체 서비스 중지
uv run killports

# Weaviate만 foreground 실행
uv run weaviate
```

`uv run all`은 다음 서비스를 순서대로 시작하고 readiness를 확인합니다.

| 서비스 | 명령 | 포트 |
|---|---|---|
| Weaviate | `uv run --package pdftablesearch weaviate` | `8113`, `8114` |
| Hybrid PDF | `uv run --package pdftablesearch opendataloader-pdf-hybrid --port 8112` | `8112` |
| API | `uv run --package pdftablesearch api start --host 127.0.0.1 --port 8111` | `8111` |
| UI | `uv run --package pdf-intelligence-web ui --host 127.0.0.1 --port 8110` | `8110` |

이 포털 런처는 Redis, Postgres, LDAP를 시작하지 않습니다. 다른 프로젝트의 Redis/Postgres/LDAP 기본 포트와 충돌하지 않도록 이 포털의 포트는 `8110-8114` 대역을 사용합니다.

각 실행의 로그는 `logs/qa_YYYYMMDD_HHMMSS/` 아래에 `weaviate.log`, `hybrid.log`, `api.log`, `ui.log`로 저장됩니다.

---

## 프로젝트 구조

```text
PDF-INTELLIGENCE-PORTAL/
├── pyproject.toml           # uv workspace root, root command aliases
├── uv.lock                  # uv workspace lockfile
├── portal_workspace/        # root scripts를 노출하기 위한 작은 Python 패키지
├── pdftablesearch/          # Python backend workspace package
│   ├── pyproject.toml       # backend 의존성 및 api/qa/weaviate scripts
│   ├── __init__.py          # 패키지 초기화, 퍼블릭 API
│   ├── web_server.py        # FastAPI 웹 서버 (세션 관리, API 라우트, 통합 검색)
│   ├── run.py               # api/pdf-portal 실행 entrypoint
│   ├── qa.py                # uv run qa 대화형 런처
│   ├── port_utils.py        # 서비스 registry, port kill/start/status
│   ├── core.py              # 코어 검색 로직
│   ├── search.py            # 검색 인터페이스
│   ├── smart_search.py      # Smart Search (LLM 표 선택)
│   ├── table_qa.py          # 표 기반 질의응답
│   ├── vectorstore.py       # 벡터 저장소 backend facade
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
│   ├── loader/              # PDF 로딩 및 테이블 추출
│       ├── __init__.py      # PDFProcessor
│       ├── html_parser.py   # HTML 테이블 추출, Markdown 변환
│       ├── json_parser.py   # JSON 메타데이터 파싱
│       ├── markdown_parser.py # Markdown 테이블 파싱
│       └── matcher.py       # HTML↔JSON 매칭
│   └── vectorstores/        # Chroma/Weaviate backend adapters
│       ├── chroma_store.py
│       ├── weaviate_store.py
│       ├── weaviate_client.py
│       ├── weaviate_schema.py
│       └── weaviate_server.py
│
├── web/                     # React frontend workspace package + npm app
│   ├── pyproject.toml       # uv wrapper scripts: ui/ui-build/ui-preview/ui-lint
│   ├── package.json         # npm/Vite 의존성의 실제 source of truth
│   ├── pdf_intelligence_web/
│   │   └── cli.py           # uv script -> npm script wrapper
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
│   └── tailwind.config.js   # Tailwind CSS 설정
│
├── db/
│   └── weaviate/            # embedded Weaviate data directory (.gitkeep only tracked)
├── tests/                   # Python 테스트
├── docs/                    # 문서
├── examples/                # 사용 예제
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
| | react-markdown + remark-gfm + rehype-raw | 10.x / 4.x / 7.x |
| | pdf.js (CDN) | 4.0 |
| **백엔드** | FastAPI | 0.100+ |
| | Uvicorn (ASGI) | 0.20+ |
| | LangChain | 0.1+ |
| **인증** | LDAP-compatible login / httpOnly cookie | ldap3 2.9+ |
| **PDF 처리** | opendataloader-pdf (hybrid) | 2.2+ |
| | PyMuPDF (fitz) | 1.24+ |
| | BeautifulSoup4 | 4.12+ |
| **임베딩** | SentenceTransformers (bge-m3) | 2.0+ |
| | z.ai Embedding API | embedding-3 |
| **벡터 DB** | Weaviate / ChromaDB fallback | 4.16+ / 0.4+ |
| **LLM** | Ollama Cloud (gpt-oss:120b) | - |
| **검색** | BM25Okapi (rank-bm25) | 0.2+ |
| **데이터** | Pandas | 2.0+ |

---

## 트러블슈팅

### 문제: 하이브리드 서버 연결 실패

```bash
# 서버 상태 확인
curl http://localhost:8112/health

# 서버가 없으면 시작
uv run qa start hybrid
```

하이브리드 서버가 없으면 표준 변환 모드로 자동 폴백됩니다。표 인식률이 떨어질 수 있으니 가능하면 실행하세요。

### 문제: Ollama API 오류

```bash
# API 연결 테스트
curl https://ollama.com/v1/chat/completions \
  -H "Authorization: Bearer $OLLAMA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-oss:120b","messages":[{"role":"user","content":"test"}],"max_tokens":10}'
```

- `.env`에서 `OLLAMA_API_KEY`가 올바른지 확인
- `ZAI_LLM_MODEL`이 Ollama에서 지원하는 모델명인지 확인

### 문제: 특정 페이지에서 표가 감지되지 않음

PyMuPDF의 `find_tables()`가 표를 감지하지 못하는 경우가 있습니다 (셀 병합, 테두리 없는 표 등). 이 경우 hybrid 파이프라인(opendataloader-pdf)에서 감지한 표가 자동으로 fallback으로 포함됩니다.

서버 로그에서 `[build] fallback` 메시지로 확인할 수 있습니다.

### 문제: PDF 업로드 실패 (ChromaDB readonly)

`VECTOR_BACKEND=chroma` fallback 사용 중 upload에서 "attempt to write a readonly database" 에러가 발생하면:

- `vectorstore.py`가 자동으로 디렉토리를 재생성하여 재시도 (최대 2회)
- 서버를 재시작하여 `/tmp` 내 임시 파일 정리

Weaviate backend로 전환하려면:

```bash
uv run killports
uv run all
```

### 문제: 페이지 번호와 내용 불일치

문서 청킹이 페이지 구분자(`<div class='page-sep' data-pn='N'>`)를 기준으로 수행되므로, 출처 페이지 번호는 실제 페이지와 일치해야 합니다. 불일치가 발생하면 문서를 다시 업로드하세요。

---

## 라이선스

이 프로젝트는 Apache License 2.0 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 확인하세요.
