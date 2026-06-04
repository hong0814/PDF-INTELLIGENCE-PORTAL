# PDF Intelligence Portal

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![Weaviate](https://img.shields.io/badge/Weaviate-1.30+-FF6B6B.svg)](https://weaviate.io/)
[![Ollama](https://img.shields.io/badge/Ollama-gpt--oss:120b-purple.svg)](https://ollama.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

금융 문서(신용심사, PF대출, 재무제표 등)를 업로드하고 자연어로 검색하는 AI 기반 문서 분석 포털입니다. 의미적 검색 + LLM 질의응답 + LDAP 인증을 통합 제공합니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **통합 문서 검색** | 표 + 텍스트를 동시에 검색하여 AI가 종합 답변 생성 (SSE 스트리밍) |
| **의미적 검색** | Weaviate hybrid search (벡터 + 키워드) + BM25 + RRF Fusion |
| **출처 팝업** | 답변 출처 클릭 시 실제 PDF 페이지 렌더링 + 하이라이트 |
| **LDAP 인증** | 기업 LDAP 서버 연동, JWT httpOnly 쿠키 인증 |
| **PII 마스킹** | 주민번호, 계좌번호, 전화번호 등 개인정보 자동 마스킹 |
| **다중 문서** | 여러 PDF를 동시에 업로드하고 선택적으로 검색 |
| **세션 관리** | 독립적인 작업 환경 관리, 검색 기록 보존 |

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (React 19)                       │
│  Zustand · Tailwind v4 · pdf.js · react-markdown            │
└──────────────┬──────────────────────────────────────────────┘
               │ HTTP / SSE
┌──────────────▼──────────────────────────────────────────────┐
│                  FastAPI (:8000)                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ auth.py  │ │ upload   │ │ search   │ │ qa       │       │
│  │ LDAP+JWT │ │ pipeline │ │ pipeline │ │ pipeline │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└────┬──────────┬──────────┬──────────┬───────────────────────┘
     │          │          │          │
     ▼          ▼          ▼          ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐
│ LDAP    │ │ Weaviate│ │ Ollama  │ │ Opendataloader│
│ :3890   │ │ :8079   │ │ Cloud   │ │ -PDF :5002   │
│         │ │ (embed) │ │ gpt-oss │ │ docling-fast │
└─────────┘ └─────────┘ └─────────┘ └──────────────┘
                 │
           ┌─────┴──────┐
           │ bge-m3     │
           │ 임베딩(CPU) │
           └────────────┘
```

---

## 빠른 시작

### 사전 요구사항

- Python 3.11+
- Node.js 18+
- OpenLDAP (인증 필요 시): `brew install openldap`

### 설치 및 실행

```bash
# 1. 저장소 클론
git clone https://github.com/hong0814/PDF-INTELLIGENCE-PORTAL.git
cd PDF-INTELLIGENCE-PORTAL

# 2. Python 가상환경 + 패키지 설치
python -m venv .venv
source .venv/bin/activate
pip install -e .

# 3. 환경 변수 설정 (.env)
cat > .env << 'EOF'
# LLM
ZAI_LLM_ENDPOINT=https://ollama.com/v1
ZAI_LLM_MODEL=gpt-oss:120b

# LDAP
LDAP_SERVER_URL=ldap://localhost:3890
LDAP_BASE_DN=dc=pdfportal,dc=local
LDAP_SERVICE_BIND_DN=cn=admin,dc=pdfportal,dc=local
LDAP_SERVICE_BIND_PASSWORD=admin

# Weaviate
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8079
WEAVIATE_GRPC_PORT=50050
VECTOR_BACKEND=weaviate

# Auth
AUTH_SECRET_KEY=dev-secret-change-me
AUTH_TOKEN_EXPIRE_HOURS=8
AUTH_PRE_AUTH_TTL_SECONDS=300
AUTH_IDLE_TIMEOUT_SECONDS=600
AUTH_WARN_BEFORE_SECONDS=60
REDIS_URL=redis://localhost:6379/0

# OTP subprocess
OTP_JAR_PATH=packages/api/lib/otp-cli.jar
OTP_SDK_PATH=
OTP_ASSTSQ=
OTP_COMPANY_CODE_DEV=tcapital
OTP_COMPANY_CODE_PROD=pcapital

# CORS
CORS_ORIGINS=http://localhost:8000,http://localhost:5173
EOF

# 4. LDAP 서버 시작 (선택)
bash scripts/ldap/start.sh

# 5. Redis 시작
redis-server --port 6379

# 6. 하이브리드 변환 서버 시작
opendataloader-pdf-hybrid --port 5002 &

# 7. 프론트엔드 빌드
cd web && npm install && npm run build && cd ..

# 7. FastAPI 서버 실행
uvicorn pdftablesearch.web_server:app --reload --port 8000

# 8. 접속
open http://localhost:8000
```

### LDAP 테스트 계정

| 계정 | 비밀번호 | 역할 |
|------|---------|------|
| `123456` | `1234` | 일반 사용자 |
| `admin` | `admin` | 관리자 |

---

## 환경 변수

### LLM

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ZAI_LLM_ENDPOINT` | `https://ollama.com/v1` | Ollama API 엔드포인트 |
| `ZAI_LLM_MODEL` | `gpt-oss:120b` | LLM 모델명 |

### LDAP 인증

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LDAP_SERVER_URL` | `ldap://localhost:3890` | LDAP 서버 URL |
| `LDAP_BASE_DN` | `dc=pdfportal,dc=local` | 검색 Base DN |
| `LDAP_SERVICE_BIND_DN` | `cn=admin,dc=pdfportal,dc=local` | 관리자 바인드 DN |
| `LDAP_SERVICE_BIND_PASSWORD` | `admin` | 관리자 비밀번호 |
| `LDAP_USE_TLS` | `false` | TLS 사용 여부 |

### Weaviate

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `WEAVIATE_HOST` | `localhost` | Weaviate 호스트 |
| `WEAVIATE_PORT` | `8079` | HTTP 포트 |
| `WEAVIATE_GRPC_PORT` | `50050` | gRPC 포트 |
| `WEAVIATE_USE_EMBEDDED` | `true` | Embedded 모드 사용 |
| `VECTOR_BACKEND` | `weaviate` | 벡터 DB 백엔드 |

### 인증

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AUTH_SECRET_KEY` | `dev-secret-change-me` | JWT 서명 시크릿 |
| `AUTH_TOKEN_EXPIRE_HOURS` | `8` | OTP 성공 후 발급되는 로그인 JWT 유효 시간 |
| `AUTH_PRE_AUTH_TTL_SECONDS` | `300` | LDAP 성공 후 OTP 입력까지 허용되는 시간 |
| `AUTH_IDLE_TIMEOUT_SECONDS` | `600` | 브라우저 idle logout 기준 시간 |
| `AUTH_WARN_BEFORE_SECONDS` | `60` | 세션 만료 경고 표시 시작 시간 |
| `REDIS_URL` | `redis://localhost:6379/0` | 로그인 세션 저장소 |
| `OTP_JAR_PATH` | `packages/api/lib/otp-cli.jar` | OTP Java CLI JAR 경로 |
| `OTP_SDK_PATH` | 빈 값 | OTP SDK JAR 경로, 없으면 `OTP_JAR_PATH`의 형제 `certifyOtp.jar` 사용 |
| `OTP_COMPANY_CODE_DEV` | `tcapital` | 개발 환경 OTP 회사 코드 |
| `OTP_COMPANY_CODE_PROD` | `pcapital` | 운영 환경 OTP 회사 코드 |

로그인 흐름은 `ID/PW LDAP 인증 -> OTP 인증 -> Redis 세션 저장 -> 서비스 이용 동의 -> 앱 진입` 순서입니다. `/api/auth/ldap`는 LDAP ID/PW만 확인하고 짧은 pre-auth JWT를 반환합니다. `/api/auth/otp`는 OTP Java subprocess 결과가 `0`일 때만 Redis에 세션을 저장하고, `auth_token` httpOnly 쿠키와 `auth_presence` 쿠키를 발급합니다.

---

## 프로젝트 구조

```
pdftablesearch/
├── pdftablesearch/                  # Python 백엔드
│   ├── web_server.py                # FastAPI 서버 (API 라우트)
│   ├── auth.py                      # LDAP + JWT 인증
│   ├── config.py                    # 환경설정 (pydantic-settings)
│   ├── core.py                      # 검색 오케스트레이션
│   ├── search.py                    # PDFTableSearch
│   ├── smart_search.py              # LLM 표 선택 검색
│   ├── hybrid_search.py             # 벡터 + BM25 + RRF Fusion
│   ├── table_utils.py               # 표 감지/매칭/병합
│   ├── table_qa.py                  # 표 Q&A
│   ├── doc_processing.py            # 문서 분할
│   ├── llm_client.py                # Ollama LLM 클라이언트
│   ├── pii_masking.py               # 개인정보 마스킹
│   ├── translation.py               # 문서 번역
│   ├── reranker.py                  # 리랭킹
│   ├── ldap_server.py               # 로컬 OpenLDAP 래퍼
│   ├── config.py                    # 환경설정 (pydantic-settings)
│   ├── vectorstores/                # Weaviate (현재 백엔드)
│   │   ├── __init__.py              # 팩토리: create_vector_store()
│   │   ├── weaviate_client.py       # embedded/local 연결
│   │   ├── weaviate_store.py        # WeaviateTableVectorStore
│   │   ├── weaviate_schema.py       # 컬렉션 스키마
│   │   └── weaviate_server.py       # Embedded 서버 진입점
│   └── loader/                      # PDF → HTML/JSON 변환
│       ├── html_parser.py
│       ├── json_parser.py
│       ├── markdown_parser.py
│       └── matcher.py
│
├── web/                             # React 프론트엔드
│   └── src/
│       ├── api/client.ts            # API 클라이언트 (SSE)
│       ├── store/useAppStore.ts     # Zustand 상태관리
│       ├── types/index.ts           # TypeScript 타입
│       └── components/
│           ├── LoginView.tsx         # LDAP 로그인
│           ├── MainScreen.tsx        # 메인 대시보드
│           ├── DocumentViewer.tsx    # PDF 뷰어
│           ├── UnifiedSearchView.tsx # 통합 검색
│           └── ...
│
├── scripts/ldap/                    # LDAP 서버 스크립트
│   ├── start.sh                     # 서버 시작
│   └── seed.ldif                    # 테스트 계정
│
├── docs/                            # 아키텍처 문서
├── pyproject.toml
└── .env
```

---

## API 엔드포인트

### 인증

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/auth/config` | OTP/idle timeout 설정 조회 |
| `POST` | `/api/auth/ldap` | LDAP 로그인 → OTP pre-auth JWT 발급 |
| `POST` | `/api/auth/login` | `/api/auth/ldap` 호환 wrapper |
| `POST` | `/api/auth/otp` | OTP subprocess 검증 → Redis 세션 저장 → 쿠키 발급 |
| `GET` | `/api/auth/verify` | Bearer token Redis 세션 검증 |
| `DELETE` | `/api/auth/session` | Bearer token Redis 세션 삭제 |
| `POST` | `/api/auth/logout` | Redis 세션 및 인증 쿠키 삭제 |
| `POST` | `/api/auth/touch` | 로그인 상태 확인 및 idle timer 유지 |

### 세션

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/sessions` | 세션 목록 |
| `POST` | `/api/sessions` | 세션 생성 |
| `GET` | `/api/sessions/:id` | 세션 상세 |
| `PUT` | `/api/sessions/:id` | 세션 수정 |
| `DELETE` | `/api/sessions/:id` | 세션 삭제 |

### 문서

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/upload` | PDF 업로드 + 표 추출 |
| `GET` | `/api/documents/pdf` | PDF 파일 |
| `GET` | `/api/documents/page-image` | 페이지 이미지 |
| `GET` | `/api/documents/tables` | 표 목록 |
| `GET` | `/api/documents/html` | 표 HTML |

### 검색

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/search` | 표 검색 (벡터 유사도) |
| `POST` | `/api/smart-search` | AI 표 선택 검색 (SSE) |
| `POST` | `/api/unified-search` | 통합 문서 검색 (SSE) |
| `POST` | `/api/unified-followup` | 후속 질문 (SSE) |

### AI

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/qa` | 표 Q&A (SSE) |
| `POST` | `/api/ask-document` | 문서 QA (SSE) |

### 기타

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/health` | 헬스체크 |
| `POST` | `/api/translate/html-pages` | 페이지별 번역 |
| `POST` | `/api/table/transpose` | 표 전치 |
| `POST` | `/api/table/calculate` | 표 계산 |

---

## 기술 스택

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

## 트러블슈팅

### LDAP 서버 연결 실패

```bash
bash scripts/ldap/start.sh   # 서버 시작
ldapsearch -x -H ldap://localhost:3890 -b "dc=pdfportal,dc=local"  # 연결 확인
```

### Weaviate 시작 실패

포트 충돌 시 기존 프로세스 종료 후 재시도:

```bash
lsof -i :8079 | grep LISTEN | awk '{print $2}' | xargs kill -9
rm -rf /tmp/weaviate-data   # 손상된 데이터 삭제
```

### 하이브리드 변환 서버 없음

서버가 없으면 표준 변환 모드로 자동 폴백됩니다. 표 인식률이 떨어질 수 있습니다.

```bash
opendataloader-pdf-hybrid --port 5002 &
curl http://localhost:5002/health  # 상태 확인
```

---

## 라이선스

MIT License. 자세한 내용은 [LICENSE](LICENSE) 파일을 확인하세요.
