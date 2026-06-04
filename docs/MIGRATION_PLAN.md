# PDF Intelligence Portal — 폐쇄망 반입 마이그레이션 계획

> 작성일: 2026-06-02

---

## 1. 개요

PDF Intelligence Portal을 인터넷이 차단된 사내 폐쇄망으로 반입하기 위한 마이그레이션 계획입니다.

### 환경 전제
- **폐쇄망**: 외부 인터넷 연결 불가
- **오픈소스 반입 시스템**: PyPI 패키지는 승인 절차를 통해 반입 가능
- **LLM**: Ollama Cloud 사용 불가 → 사내 LLM 서버 필요
- **LDAP**: 사내 LDAP 서버 연동 필요

### 반입 대상 아키텍처 변화

| 컴포넌트 | 현재 (개발) | 반입 후 (사내) |
|----------|------------|---------------|
| LLM | Ollama Cloud (gpt-oss:120b) | 사내 Ollama/vLLM 서버 |
| 임베딩 모델 | HuggingFace 자동 다운로드 | weight 파일 수동 반입 |
| Weaviate | Embedded (자동 다운로드) | 바이너리 수동 반입 또는 Docker |
| LDAP | 로컬 OpenLDAP (테스트) | 사내 LDAP 서버 |
| PDF 변환 | opendataloader-pdf hybrid 서버 | 동일 (로컬 구동) |
| PyPI 패키지 | uv pip install | 오픈소스 반입 시스템 |

---

## 2. 반입 체크리스트

### Phase 1: 사전 준비 (외부망에서 수행)

#### 2.1 Python 패키지 수집

uv를 사용하여 오프라인 설치용 패키지를 수집합니다.

```bash
# 1. uv 설치 (외부망)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 전체 의존성을 wheel + sdist로 다운로드
mkdir -p offline_packages
uv pip compile pyproject.toml -o requirements.txt
uv pip download -r requirements.txt -d offline_packages/

# 또는 직접 지정
uv pip download -d offline_packages/ \
  fastapi uvicorn python-multipart beautifulsoup4 \
  pandas langchain langchain-community langchain-core \
  langchain-openai langchain-text-splitters \
  weaviate-client requests pydantic pydantic-settings \
  python-dotenv tenacity tqdm sentence-transformers \
  pymupdf rank-bm25 cryptography ldap3 PyJWT \
  "opendataloader-pdf[hybrid]" torch torchvision

# 3. 대상 플랫폼 지정 (사내 서버가 Linux인 경우)
uv pip download -d offline_packages/ \
  --platform linux/x86_64 \
  --python-version 3.11 \
  -r requirements.txt
```

**예상 패키지 수**: ~160개 (트랜지티브 의존성 포함)
**예상 총 크기**: ~15-20 GB (torch, torchvision 포함)

#### 2.2 임베딩 모델 (bge-m3)

```
모델: BAAI/bge-m3
크기: ~2.1 GB
위치: ~/.cache/huggingface/hub/models--BAAI--bge-m3/
```

**반입 방법**:
```bash
# 1. 캐시 디렉토리 압축
cd ~/.cache/huggingface/hub/
tar czf bge-m3-model.tar.gz models--BAAI--bge-m3/

# 2. 또는 명시적 다운로드
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('BAAI/bge-m3')
model.save('/path/to/export/bge-m3/')
"
# → /path/to/export/bge-m3/ 를 tar로 압축
```

**사내 배치**:
```bash
# 방법 A: 캐시 복원
mkdir -p ~/.cache/huggingface/hub/
tar xzf bge-m3-model.tar.gz -C ~/.cache/huggingface/hub/

# 방법 B: 로컬 경로 로드 (config.py 수정)
# model = SentenceTransformer('/opt/models/bge-m3/')
```

**⚠ config.py 수정 필요**: `LOCAL_EMBEDDING_MODEL_PATH` 설정 추가

#### 2.3 Weaviate Embedded 바이너리

```
바이너리: weaviate v1.30.5
크기: ~360 MB (캐시 포함)
위치: ~/.cache/weaviate-embedded/
```

**반입 방법**:
```bash
# 전체 캐시 압축
tar czf weaviate-embedded.tar.gz -C ~/.cache/weaviate-embedded/ .
```

**사내 배치**:
```bash
mkdir -p ~/.cache/weaviate-embedded/
tar xzf weaviate-embedded.tar.gz -C ~/.cache/weaviate-embedded/
chmod +x ~/.cache/weaviate-embedded/weaviate-*
```

**대안**: Docker 이미지로 반입
```bash
docker pull cr.weaviate.io/semitechnologies/weaviate:1.30.5
docker save -o weaviate-1.30.5.tar cr.weaviate.io/semitechnologies/weaviate:1.30.5
# 사내에서: docker load -i weaviate-1.30.5.tar
```

#### 2.4 opendataloader-pdf hybrid 서버

opendataloader-pdf의 docling-fast 서버는 내부적으로 docling + easyocr을 사용합니다.

**반입 대상**:
- `opendataloader-pdf[hybrid]` 패키지 (offline_packages에 포함)
- EasyOCR 모델 파일 (자동 다운로드됨 → 수동 반입 필요)

```bash
# EasyOCR 모델 캐시 위치
find ~/.EasyOCR/ -type f  # 또는 ~/.cache/easyocr/
tar czf easyocr-models.tar.gz -C ~/.EasyOCR/ .
```

### Phase 2: 오픈소스 반입 승인

#### 2.5 패키지 승인 목록

**핵심 패키지 (반입 승인 필요)**:

| 패키지 | 버전 | 라이선스 | 용도 |
|--------|------|---------|------|
| `torch` | 2.11.0 | BSD-3 | 임베딩 추론, docling |
| `weaviate-client` | 4.21.2 | BSD-3 | 벡터 DB 클라이언트 |
| `weaviate-client` | 4.21.2 | BSD-3 | 벡터 DB |
| `langchain` | 1.2.15 | MIT | RAG 프레임워크 |
| `sentence-transformers` | 5.4.1 | Apache-2.0 | 임베딩 |
| `fastapi` | 0.135.3 | MIT | 웹 서버 |
| `pydantic` | 2.x | MIT | 데이터 검증 |
| `PyMuPDF` | 1.27.2 | AGPL-3.0 | **⚠ 주의** PDF 처리 |
| `docling` | 2.88.0 | MIT | PDF 변환 |
| `easyocr` | 1.7.2 | Apache-2.0 | OCR |
| `cryptography` | 48.0.0 | Apache-2.0 | 암호화 |
| `ldap3` | 2.9.0 | LGPL-3.0 | LDAP 클라이언트 |
| `PyJWT` | 2.8.0 | MIT | JWT 인증 |
| `grpcio` | 1.78.0 | Apache-2.0 | Weaviate gRPC |
| `scikit-learn` | 1.8.0 | BSD-3 | BM25 등 |
| `transformers` | 5.5.4 | Apache-2.0 | 모델 로딩 |

**⚠ 라이선스 주의사항**:
- **PyMuPDF (AGPL-3.0)**: 상업적 사내 사용은 가능하나, 수정 후 배포 시 소스 공개 의무. 수정하지 않고 사용하면 문제 없음.
- **ldap3 (LGPL-3.0)**: 동적 링크하므로 문제 없음.

### Phase 3: 사내 인프라 구축

#### 2.6 LLM 서버

Ollama Cloud 대체 방안:

| 옵션 | 설명 | 요구사항 |
|------|------|---------|
| **사내 Ollama** | GPU 서버에 Ollama 설치 | NVIDIA GPU (VRAM 80GB+ 추천) |
| **vLLM** | 고성능 LLM 서빙 | NVIDIA GPU |
| **TGI** | HuggingFace Text Generation Inference | NVIDIA GPU |

**모델 반입**:
```bash
# 외부망에서 모델 다운로드
ollama pull gpt-oss:120b
# 또는 GGUF 파일 직접 다운로드

# 모델 파일 압축
tar czf llm-model.tar.gz ~/.ollama/models/

# 사내 서버에 복원
tar xzf llm-model.tar.gz -C /opt/ollama/
```

**config.py 설정**:
```bash
ZAI_LLM_ENDPOINT=http://사내-llm서버:11434/v1
ZAI_LLM_MODEL=gpt-oss:120b  # 또는 사내 모델명
```

#### 2.7 사내 LDAP 연동

```bash
# .env 설정
LDAP_SERVER_URL=ldap://사내-ldap서버:389
LDAP_BASE_DN=dc=회사,dc=com
LDAP_BIND_DN=cn=svc_pdfportal,dc=회사,dc=com
LDAP_BIND_PASSWORD=<사내-비밀번호>

# 사용자 검색 필드 확인 필요 (uid vs sAMAccountName)
LDAP_USER_SEARCH_FIELD=uid  # OpenLDAP
# LDAP_USER_SEARCH_FIELD=sAMAccountName  # Active Directory
```

**auth.py 수정 필요 여부**: 검색 필드가 `uid`가 아닌 경우 `auth.py` 수정 필요

---

## 3. 반입 패키지 목록 (전체)

### 3.1 직접 의존성 (pyproject.toml)

```
fastapi>=0.100.0
uvicorn>=0.20.0
python-multipart>=0.0.5
beautifulsoup4>=4.12.0
pandas>=2.0.0
langchain>=0.1.0
langchain-community>=0.0.20
langchain-core>=0.1.0
langchain-openai>=0.0.5
langchain-text-splitters>=0.0.1
opendataloader-pdf[hybrid]>=2.2.1
weaviate-client>=4.0.0
requests>=2.31.0
pydantic>=2.5.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
tenacity>=8.2.0
tqdm>=4.66.0
sentence-transformers>=2.0.0
pymupdf>=1.24.0
rank-bm25>=0.2.2
cryptography>=41.0.0
ldap3>=2.9.0
PyJWT>=2.8.0
weaviate-client>=4.0.0
```

### 3.2 수동 반입 아티팩트

| 아티팩트 | 크기 | 반입 방법 |
|----------|------|----------|
| `bge-m3` 모델 weight | ~2.1 GB | tar 압축 → 오픈소스 반입 또는 USB |
| Weaviate embedded 바이너리 | ~360 MB | tar 압축 또는 Docker 이미지 |
| EasyOCR 모델 파일 | ~200 MB | tar 압축 |
| LLM 모델 (gpt-oss:120b) | ~65 GB | 별도 GPU 서버 반입 |
| Python 패키지 wheel 모음 | ~15-20 GB | 오픈소스 반입 시스템 |

**총 반입 크기**: ~83 GB (LLM 모델 제외 시 ~18 GB)

---

## 4. 설치 순서 (사내 폐쇄망)

```bash
# 1. uv 바이너리 반입 (오픈소스 반입 시스템 또는 USB)
# 외부망에서 다운로드: https://github.com/astral-sh/uv/releases
# linux-x86_64용: uv-x.xx.x-linux-x86_64.tar.gz
chmod +x uv
# 또는 PATH에 등록

# 2. Python 3.11 설치 (사내 표준)
uv python install 3.11  # 또는 사내 Python 배포 사용

# 3. 가상환경 생성 + 오프라인 패키지 설치
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install --no-index --find-links=offline_packages/ -e .

# 4. 모델 배치
tar xzf bge-m3-model.tar.gz -C ~/.cache/huggingface/hub/
tar xzf weaviate-embedded.tar.gz -C ~/.cache/weaviate-embedded/
tar xzf easyocr-models.tar.gz -C ~/.EasyOCR/

# 5. 환경 설정
cp .env.example .env
# .env 수정: LDAP, LLM, Weaviate, CORS 설정

# 6. 프론트엔드 빌드 (Node.js 필요)
cd web && npm install --offline && npm run build && cd ..

# 7. 서비스 구동
opendataloader-pdf-hybrid --port 5002 &
uv run uvicorn pdftablesearch.web_server:app --host 0.0.0.0 --port 8000
```

---

## 5. config.py 변경 사항

폐쇄망 반입을 위해 `config.py`에 추가 필요한 설정:

```python
# 임베딩 모델 로컬 경로 (폐쇄망에서 HuggingFace 캐시 대신)
local_model_path: str = ""  # 예: /opt/models/bge-m3/

# Weaviate 바이너리 경로 (명시적 지정)
weaviate_binary_path: str = ""  # 예: /opt/weaviate/weaviate-v1.30.5
```

`local_embeddings.py` 수정:
```python
# 기존: model = SentenceTransformer("BAAI/bge-m3")
# 폐쇄망: model = SentenceTransformer(settings.local_model_path or "BAAI/bge-m3")
```

---

## 6. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| HuggingFace 자동 다운로드 | 임베딩/OCR 모델 로드 실패 | 모델 weight 수동 반입, 로컬 경로 설정 |
| Weaviate embedded 자동 다운로드 | 서버 시작 실패 | 바이너리 수동 반입 또는 Docker |
| EasyOCR 자동 다운로드 | OCR 실패 | 모델 파일 수동 반입 |
| torch CUDA 없음 | GPU 가속 불가 → CPU 추론 | CPU 모드로 동작 (속도 저하) |
| PyMuPDF AGPL 라이선스 | 법적 리스크 | 수정하지 않고 사용, 또는 PyPDF로 대체 검토 |
| 사내 LLM 미구축 | AI 기능 전체 불가 | vLLM/Ollama 사내 구축 선행 |
| 패키지 의존성 충돌 | 설치 실패 | uv pip download로 플랫폼 고정하여 수집 |
| Node.js 미설치 | 프론트엔드 빌드 불가 | 빌드된 static 파일 반입 |

---

## 7. 권장 반입 순서

1. **사내 LLM 서버 구축** (GPU 서버 + Ollama/vLLM + 모델 반입)
2. **uv 바이너리 반입** (https://github.com/astral-sh/uv/releases 에서 Linux용 다운로드)
3. **Python 패키지 승인 요청** (~160개, 오픈소스 반입 시스템)
4. **모델 아티팩트 반입** (bge-m3, Weaviate 바이너리, EasyOCR)
5. **소스코드 + 빌드된 프론트엔드 반입**
6. **사내 LDAP 연동 설정** (Base DN, Bind DN, 검색 필드)
7. **통합 테스트** (업로드 → 검색 → QA 플로우)
8. **보안 감사** (PII 마스킹, 인증, CORS 확인)
