# PDF Intelligence Portal — 전체 아키텍처 상세 설명

> 최종 업데이트: 2026-05-28

---

## 목차

1. [파일 저장소 구조](#1-파일-저장소-구조)
2. [PDF 업로드 & 문서 파싱 전체 흐름](#2-pdf-업로드--문서-파싱-전체-흐름)
3. [테이블 제목 추출 — 3단계 폴백](#3-테이블-제목-추출--3단계-폴백)
4. [임베딩 (Embedding)](#4-임베딩-embedding)
5. [Vector DB (ChromaDB) 저장](#5-vector-db-chromadb-저장)
6. [암호화 레이어](#6-암호화-레이어)
7. [RAG 검색 (문서 검색 탭)](#7-rag-검색-문서-검색-탭)
8. [PII 마스킹](#8-pii-마스킹)
9. [파일 생명주기 (생성 / 삭제)](#9-파일-생명주기-생성--삭제)
10. [전체 데이터 흐름 요약](#10-전체-데이터-흐름-요약)
11. [주요 기술적 특징](#11-주요-기술적-특징)
12. [관련 파일 인덱스](#12-관련-파일-인덱스)

---

## 1. 파일 저장소 구조

서버 실행 시 생성되는 모든 파일의 디스크 상 위치:

```
/tmp/
├── pdf_upload_<uuid>/              ← PDF 원본 + 변환 산출물
│   ├── hcs.pdf                     ← 업로드된 원본 PDF
│   ├── hcs/                        ← opendataloader-pdf 변환 결과
│   │   ├── hcs.html                ← 전체 페이지 HTML (page-sep 구분자 포함)
│   │   ├── hcs.json                ← 표 메타데이터 (bbox, 페이지 번호)
│   │   ├── hcs.md                  ← Markdown 변환 결과
│   │   └── standard/               ← 표준 변환(비 hybrid) 결과
│   │       └── hcs.html            ← 중첩 테이블 보존용 HTML
│
├── pdf_chroma_<uuid>/              ← 표(Table) 벡터 DB
│   └── chroma.sqlite3              ← ChromaDB 테이블 임베딩 저장
│
├── pdf_docchunks_<uuid>/           ← 텍스트 청크 벡터 DB
│   └── chroma.sqlite3              ← ChromaDB 텍스트 청크 임베딩 저장
│
~/.pdftablesearch/
└── fernet.key                      ← Fernet 암호화 키 (자동 생성, chmod 600)
```

### 세션별 독립성

각 세션마다 고유한 임시 디렉토리가 할당되므로, 여러 세션이 동시에 존재해도 데이터가 섞이지 않습니다.

---

## 2. PDF 업로드 & 문서 파싱 전체 흐름

### 2.1 업로드 진입점 (`POST /api/upload`)

**코드 위치**: `web_server.py` L1683

```
브라우저 → POST /api/upload (multipart/form-data: files + X-Session-ID 헤더)
```

#### 세션 확인/생성

```python
# web_server.py L1691
if session_id in _sessions:
    session = _sessions[session_id]          # 기존 세션 재사용
    upload_dir = session["upload_dir"]
    chroma_dir = session["chroma_dir"]
else:
    upload_dir = tempfile.mkdtemp(prefix="pdf_upload_")    # 새 임시 디렉토리
    chroma_dir = tempfile.mkdtemp(prefix="pdf_chroma_")
    doc_chunks_dir = tempfile.mkdtemp(prefix="pdf_docchunks_")
    session = { upload_dir, chroma_dir, doc_chunks_dir, pdfs: {}, ... }
    _sessions[session_id] = session
```

#### PDF 파일 저장

```python
# web_server.py L1725
dest = Path(upload_dir) / filename           # 예: /tmp/pdf_upload_abc123/hcs.pdf
with open(dest, "wb") as f:
    content = await upload.read()
    f.write(content)
```

---

### 2.2 PDF → HTML/JSON/MD 변환

**코드 위치**: `loader/__init__.py` → `PDFProcessor.convert_pdf()`

```python
# loader/__init__.py L71
def convert_pdf(self, pdf_path, output_dir=None, use_hybrid=True):
    target_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="pdftablesearch_"))
    target_dir.mkdir(parents=True, exist_ok=True)

    convert_params = {
        "input_path": str(validated_path),
        "output_dir": str(target_dir),
        "format": "html, json, markdown",
        "html_page_separator": "<div class='page-sep' data-pn='%page-number%'></div>",
    }

    if use_hybrid:
        convert_params["hybrid"] = "docling-fast"           # OCR 기반 고품질 변환
        convert_params["hybrid_url"] = "http://localhost:5002"
        try:
            opendataloader_pdf.convert(**convert_params)
        except Exception:
            # Hybrid 실패 시 표준 변환으로 자동 fallback
            convert_params.pop("hybrid")
            convert_params.pop("hybrid_url")
            opendataloader_pdf.convert(**convert_params)
```

#### 변환 산출물

| 파일 | 내용 | 용도 |
|------|------|------|
| `{name}.html` | 전체 페이지 HTML. `<div class='page-sep' data-pn='N'>`로 페이지 구분 | 표 추출, 텍스트 청킹 |
| `{name}.json` | 표 메타데이터 (`kids` 배열에 `bounding box`, `page number`) | bbox, 페이지 번호 |
| `{name}.md` | Markdown 변환 결과 | 표 제목 fallback 추출 |

#### HTML 페이지 구분자

```html
<!-- 각 페이지 시작 시 삽입 -->
<div class='page-sep' data-pn='1'>...</div>
<div class='page-sep' data-pn='2'>...</div>
...
```

이 구분자로 텍스트 청킹 시 페이지 경계를 보존합니다.

---

### 2.3 HTML에서 표 추출

**코드 위치**: `loader/html_parser.py` → `extract_html_tables_from_file()`

#### 과정

1. **BeautifulSoup**으로 HTML에서 모든 `<table>` 태그 찾기
2. 각 테이블의 **제목(title)** 추출:
   ```python
   # 테이블 바로 앞의 h1~h6 태그 텍스트
   prev_sibling = table_tag.find_previous_sibling(["h1", "h2", "h3", "h4", "h5", "h6"])
   if prev_sibling:
       title = prev_sibling.get_text(strip=True)
       # "1. 가나다." 같은 번호 prefix 제거
       title = re.sub(r"^[\d\w가나다라마바사아자차카타파하]+\.\s+", "", title)
   ```
3. **컨텍스트(context)** 수집: 테이블 앞 5개 + 뒤 2개 형제 요소 텍스트
4. **HTML 정제** (`sanitize_table_html`):
   - `<script>` 태그 제거
   - 이벤트 핸들러 속성 제거 (`onclick`, `onmouseover` 등)
   - `javascript:` URL 제거
5. 반환: `(table_html, index, title, context)` 튜플 리스트

---

### 2.4 JSON에서 메타데이터 추출

**코드 위치**: `loader/json_parser.py` → `parse_json_metadata()`

#### JSON 구조

```json
{
  "kids": [
    {
      "type": "table",
      "bounding box": [x0, y0, x1, y1],
      "page number": 3,
      "id": 0,
      "rows": [
        { "cells": [ { "kids": [ { "content": "셀 내용" } ] } ] }
      ]
    }
  ]
}
```

#### 추출 결과

```python
{
    "page_number": 3,
    "bounding_box": [x0, y0, x1, y1],   # PDF 좌표계 (원점 왼쪽 하단)
    "index": 0,
    "id": 0,
    "table_data": { ... }                # 원본 JSON 엔트리 전체
}
```

---

### 2.5 Markdown에서 표 제목 추출 (Fallback)

**코드 위치**: `loader/markdown_parser.py` → `extract_table_info()`

HTML에서 제목을 얻지 못한 경우 Markdown 파일에서 대체 추출:

```python
# 표 시작 라인에서 위로 최대 15줄 역탐색
for offset in range(1, 16):
    check_line = table_line - offset
    line = lines[check_line].strip()

    # 우선순위 1: # <제목> (꺾쇠 안의 텍스트)
    angle_match = re.match(r"^#{1,6}\s*<([^>]+)>", line)

    # 우선순위 2: # 제목 (일반 헤더)
    header_match = re.match(r"^#{1,6}\s+(.+)$", line)

    # 우선순위 3: - 제목 (리스트)
    list_match = re.match(r"^[-\*]+\s*(.+)$", line)
```

- 제목 후보가 숫자/기호만이면 제외
- 페이지 추정: JSON 메타데이터의 페이지 분포에 따라 비례 분배

---

### 2.6 HTML ↔ JSON 매칭

**코드 위치**: `loader/matcher.py` → `find_best_json_match()`

HTML에서 추출한 표와 JSON에서 추출한 메타데이터를 **Jaccard 유사도**로 매칭:

```python
def calculate_table_similarity(html_content, json_meta):
    # HTML 표 텍스트와 JSON 셀 데이터를 정규화
    html_normalized = html_content.lower().replace(" ", "")
    json_normalized = json_content.lower().replace(" ", "")

    # 포함 관계면 0.9 (높은 점수)
    if json_normalized in html_normalized:
        return 0.9

    # Jaccard 유사도
    html_words = set(html_normalized.split())
    json_words = set(json_normalized.split())
    return len(intersection) / len(union)
```

- **임계값**: 0.3 이하면 매칭 실패 → bbox 없이 페이지 추정만 사용
- 한 번 매칭된 JSON 인덱스는 재사용 불가 (`used_indices` 세트 관리)
- 매칭 성공 시: JSON에서 **정확한 페이지 번호 + bounding box** 획득

---

### 2.7 PyMuPDF 보강 테이블 감지

**코드 위치**: `web_server.py` L708 → `_build_tables_from_pymupdf()`

hybrid/HTML 감지 결과에 PyMuPDF(`fitz`) 감지를 보강:

#### 과정

1. **PyMuPDF 표 감지**: 각 페이지에서 `page.find_tables()` 실행
2. **면적 필터**: 5000px² 미만 표 제거 (노이즈)
3. **내부 테이블 감지**: 바깥 테이블에 완전히 포함된 내부 테이블 분리 (중첩 표)
4. **hybrid HTML 매칭**:
   - PyMuPDF 표 ↔ hybrid HTML 표를 **텍스트 유사도 + Y좌표 오버랩**으로 매칭
   - 매칭 성공 시 **hybrid bbox를 우선 사용** (PyMuPDF bbox는 fallback)
5. **표준 변환 보강**: 중첩 테이블이 있는 경우 → `standard/` HTML에서 테이블 추출
6. **Fallback 복구**: PyMuPDF만 감지한 표도 `pymupdf` 출처로 추가

#### Bounding Box 좌표 변환

```python
# PyMuPDF bbox: 원점 왼쪽 상단, Y축 아래쪽
# PDF 좌표계: 원점 왼쪽 하단, Y축 위쪽
pdf_bbox = [fbbox[0], page_h - fbbox[3], fbbox[2], page_h - fbbox[1]]
```

---

### 2.8 다중페이지 표 감지

**코드 위치**: `web_server.py` L917 → `_detect_multipage_tables()`

```
p.7 마지막 표 + p.8 첫 번째 표 → 연속 표 후보
```

#### 감지 조건

1. **인접 페이지**: `pb == pa + 1`
2. **위치 조건**:
   - A페이지 표가 **하단 근처** (`bbox.y0 < 200`)
   - B페이지 표가 **상단 근처** (`bbox.y3 > 400`)
3. **컬럼 수**: 같으면 후보 포함. 달라도 B페이지 표가 **최상단**이면 포함 (`force_include`)
4. **추이적 폐쇄**: A→B, B→C면 `[A, B, C]` 체인 생성

#### 결과

`table_group_suggestions`로 프론트엔드에 전달 → **사용자 확인 팝업**으로 병합 여부 결정

---

## 3. 테이블 제목 추출 — 3단계 폴백

| 우선순위 | 방법 | 소스 파일 | 함수 |
|----------|------|-----------|------|
| **1순위** | HTML에서 표 앞 `<h1>`~`<h6>` 태그 텍스트 | `html_parser.py` | `extract_html_tables_from_file()` |
| **2순위** | Markdown에서 표 위 `# 제목` 헤더 | `markdown_parser.py` | `extract_table_info()` |
| **3순위** | 제목 없음 → `"(제목 없음)"` | — | — |

### HTML 제목 추출 상세

```python
# html_parser.py
prev_sibling = table_tag.find_previous_sibling(["h1", "h2", "h3", "h4", "h5", "h6"])
if prev_sibling:
    title = prev_sibling.get_text(strip=True)
    # "1. 가나다." 같은 번호 prefix 제거
    title = re.sub(r"^[\d\w가나다라마바사아자차카타파하]+\.\s+", "", title)
```

### Markdown 제목 추출 상세 (최대 15줄 역탐색)

```python
# markdown_parser.py
for offset in range(1, 16):
    check_line = table_line - offset
    # #{1,6} <제목> → 꺾쇠 안의 텍스트
    # #{1,6} 제목 → 일반 헤더 텍스트
    # - 제목 → 리스트 항목 텍스트
    # 조건: len > 2, 숫자/기호만이면 제외
```

---

## 4. 임베딩 (Embedding)

### 모델: `BAAI/bge-m3` (SentenceTransformers)

**코드 위치**: `local_embeddings.py`

```python
os.environ["HF_HUB_OFFLINE"] = "1"  # 오프라인 모드 (캐시된 모델만 사용)

model = SentenceTransformer("BAAI/bge-m3", device="cpu", trust_remote_code=True)
```

| 항목 | 값 |
|------|-----|
| **모델** | BAAI/bge-m3 |
| **벡터 차원** | 1024 |
| **지원 언어** | 한국어 + 100+ 언어 |
| **실행 환경** | 로컬 CPU (API 키 불필요) |
| **로딩 시점** | 서버 시작 시 1회 (`lifespan`에서 로드) |
| **재사용** | 전역 `_embeddings` 객체로 모든 세션에서 공유 |

### 임베딩 생성 시점

| 시점 | 대상 | 위치 |
|------|------|------|
| PDF 업로드 | 표 HTML + 제목 + 컨텍스트 | `vectorstore.add_documents(all_docs)` |
| PDF 업로드 | 텍스트 청크 | `_chunk_and_index_session()` |
| 검색 시 | 사용자 쿼리 | `table_store.similarity_search(query=...)` |

### 임베딩 대상 (page_content)

```python
# 표 Document의 page_content 구성
content_parts = []
if table_title:
    content_parts.append(table_title)     # 예: "재무상태표"
if table_context:
    content_parts.append(table_context)   # 주변 텍스트
content_parts.append(table_html)          # <table>...</table> HTML
content = "\n".join(content_parts)
```

---

## 5. Vector DB (ChromaDB) 저장

### 5.1 두 개의 독립 컬렉션

| 컬렉션 | 디렉토리 | 내용 | 컬렉션명 | 생성 시점 |
|--------|----------|------|----------|----------|
| **표 임베딩** | `pdf_chroma_<uuid>/` | 표 HTML + 제목 + 컨텍스트 | `pdf_tables` | PDF 업로드 시 |
| **텍스트 청크** | `pdf_docchunks_<uuid>/` | 텍스트 청크 | `doc_chunks_<session_id>` | PDF 업로드 시 |

### 5.2 테이블 ChromaDB 저장

**코드 위치**: `web_server.py` L1834

```python
embeddings = _get_embeddings()
vector_store = TableVectorStore(embeddings=embeddings, persist_dir=chroma_dir)
vector_store.add_documents(all_docs)
```

#### 저장되는 Document 구조

```python
Document(
    page_content="{table_title}\n{table_context}\n{table_html}",  # 임베딩 대상
    metadata={
        "page_number": 3,
        "bounding_box": [x0, y0, x1, y1],
        "table_id": "table_3_0",
        "document_name": "hcs",                    # 확장자 없음
        "table_html": "<table>...</table>",
        "table_title": "재무상태표",
        "table_context": "주요 재무 지표...",
        "_encrypted": True,                        # 암호화 활성화 시
    }
)
```

### 5.3 텍스트 청크 ChromaDB 저장

**코드 위치**: `web_server.py` L356 → `_chunk_and_index_session()`

#### 청킹 과정

1. HTML 파일에서 `<div class='page-sep' data-pn='N'>` 로 페이지 분할
2. 각 페이지 HTML에서 **표(`<table>`) 제거** → 텍스트만 남김
3. 텍스트를 **문단 단위**로 분할 (빈 줄 기준)
4. 각 문단을 청크로 ChromaDB에 저장

```python
# 페이지 분할
parts = PAGE_SEP_RE.split(html_content)
# parts[0] = 첫 separator 전
# parts[1] = 페이지 번호, parts[2] = 해당 페이지 HTML, ...

# 문단 분할
para_chunks = _split_html_by_paragraphs(page_html, pdf_name, page_num)
```

#### 청크 메타데이터

```python
{
    "source_pdf": "hcs.pdf",
    "chunk_index": 42,
    "page_number": 7,
    "pdf_page_count": 30,
    "paragraph_id": "hcs_p7_para3",
}
```

### 5.4 BM25 인덱스 구축

**코드 위치**: `web_server.py` L450

```python
from rank_bm25 import BM25Okapi

tokenized_corpus = [_tokenize_korean(chunk) for chunk in all_chunks]
bm25 = BM25Okapi(tokenized_corpus)

session["bm25_index"] = bm25             # 인메모리 (서버 재시작 시 소멸)
session["bm25_chunks"] = all_chunks       # 원본 텍스트
session["bm25_metadatas"] = all_metadatas  # 메타데이터
```

---

## 6. 암호화 레이어

**코드 위치**: `encryption.py`

### 개요

ChromaDB에 저장되는 `page_content`를 Fernet 대칭 암호화로 보호합니다.

### 암호화 흐름

```
저장:
  plaintext → 임베딩 생성(평문) → page_content만 Fernet 암호화 → 디스크에는 암호문

검색:
  쿼리 → 임베딩 → ChromaDB 검색(암호문 그대로) → 결과 복호화 → 반환
```

### 설정

| 항목 | 값 |
|------|-----|
| **기본값** | 활성화 (`PDFTABLE_ENCRYPTION_ENABLED=true`) |
| **비활성화** | `PDFTABLE_ENCRYPTION_ENABLED=false` |
| **키 소스** | 1순위: `PDFTABLE_ENCRYPTION_KEY` 환경변수, 2순위: `~/.pdftablesearch/fernet.key` |
| **키 자동 생성** | 활성화 상태에서 키가 없으면 자동 생성 |
| **권한** | `fernet.key` 파일은 `chmod 600` (소유자만 읽기) |

### 메타데이터 마커

```python
# 암호화된 문서의 metadata에 마커 추가
meta["_encrypted"] = True

# 검색 시 마커 확인 후 복호화
if is_encrypted_metadata(doc.metadata):
    doc = Document(page_content=decrypt_text(doc.page_content), ...)
```

---

## 7. RAG 검색 (문서 검색 탭)

### 7.1 통합 검색 흐름 (`POST /api/unified-search`)

**코드 위치**: `web_server.py` L2661

```
사용자 질문 → 3가지 검색 병렬 실행 → RRF Fusion → LLM 답변 생성
```

---

### Phase 1: 표 벡터 검색

```python
# web_server.py L2686
table_store = TableVectorStore(
    embeddings=embeddings,
    persist_dir=session["chroma_dir"],
)
table_results = table_store.similarity_search(query=body.query, k=10)
```

- ChromaDB `pdf_tables` 컬렉션에서 상위 10개 표 검색
- 암호화 활성화 시 자동 복호화

---

### Phase 2: 텍스트 하이브리드 검색 (Vector + BM25 → RRF)

#### Vector 검색

```python
# web_server.py L2695
doc_store = TableVectorStore(
    embeddings=embeddings,
    persist_dir=session["doc_chunks_dir"],
    collection_name=f"doc_chunks_{session_id}",
)
doc_vector_results = doc_store.similarity_search(query=body.query, k=8)
```

#### BM25 키워드 검색

```python
# web_server.py L2703
bm25 = session["bm25_index"]                    # 업로드 시 구축됨
tokenized_query = _tokenize_korean(body.query)
scores = bm25.get_scores(tokenized_query)
top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:8]
bm25_results = [(idx, scores[idx]) for idx in top_indices if scores[idx] > 0]
```

#### RRF (Reciprocal Rank Fusion)

```python
# web_server.py L2714
rrf_k = 60  # 표준값 (원 논문 기준)

# Vector 검색 결과에 RRF 점수 부여
for rank, (doc, _score) in enumerate(doc_vector_results):
    rrf_scores[idx] += 1.0 / (rrf_k + rank + 1)

# BM25 검색 결과에 RRF 점수 부여
for rank, (idx, _score) in enumerate(bm25_results):
    rrf_scores[idx] += 1.0 / (rrf_k + rank + 1)

# 두 검색에 모두 나타나는 청크가 더 높은 점수를 받음
fused_indices = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:5]
```

---

### Phase 3: LLM 컨텍스트 구성

상위 5개 텍스트 청크 + 상위 3개 표를 LLM에 전달:

```
[텍스트출처1] {PII 마스킹된 텍스트 청크 1}
[텍스트출처2] {PII 마스킹된 텍스트 청크 2}
...
[표출처1] 제목: {표 제목}\n{PII 마스킹된 표 HTML}
[표출처2] ...
```

#### PII 마스킹

- 텍스트 청크: `mask_pii_text(chunk_text)`
- 표 제목: `mask_pii_text(title)`
- 표 HTML: `mask_pii_in_html(table_html)` (BeautifulSoup으로 텍스트 노드만 마스킹)

---

### Phase 4: LLM 스트리밍 답변 (Ollama `gpt-oss:120b`)

**코드 위치**: `web_server.py` L2825

```python
client = ZaiLLMClient(max_retries=2)
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user",   "content": user_prompt},
]
for chunk in client._llm.stream(messages):
    token = chunk.content
    accumulated += token
```

#### System Prompt 규칙

```
1. 문서에 없는 내용은 추측하지 마세요
2. 구체적인 수치, 날짜, 업체명 등을 정확히 인용하세요
3. 한국어로 존댓말(~습니다, ~합니다, ~세요)을 사용하여 마크다운 형식으로 답변하세요
4. HTML 태그를 사용하지 마세요
5. 출처 번호를 [텍스트출처N] 또는 [표출처N] 형식으로 본문에 인용하세요
6. 답변 마지막 줄에 '사용출처: 텍스트1,표2' 형식으로 사용한 출처만 표시하세요
```

---

### Phase 5: 출처 파싱 & 필터링

**코드 위치**: `web_server.py` L2855

LLM 답변에서 사용된 출처만 추출:

#### 1. `사용출처:` 줄 파싱

```python
used_match = re.search(r'사용출처:\s*(.+)', accumulated)
if used_match:
    for part in used_match.group(1).split(','):
        part = part.strip().replace('【', '').replace('」', '')
        if part.startswith('텍스트'):
            used_text_indices.append(int(num_str) - 1)
        elif part.startswith('표'):
            used_table_indices.append(int(num_str) - 1)
```

#### 2. 인라인 인용 파싱

```python
# [텍스트출처N] 또는 【텍스트출처N】 모두 매칭
for m in re.finditer(r'[\[【]텍스트출처(\d+)[\]】]', accumulated):
    idx = int(m.group(1)) - 1
    if idx not in used_text_indices:
        used_text_indices.append(idx)
for m in re.finditer(r'[\[【]표출처(\d+)[\]】]', accumulated):
    idx = int(m.group(1)) - 1
    if idx not in used_table_indices:
        used_table_indices.append(idx)
```

#### 3. 필터링

```python
# 사용된 출처만 filtered_sources에 포함
if used_text_indices or used_table_indices:
    for src in all_sources:
        if src["type"] == "text" and text_counter in used_text_indices:
            filtered_sources.append(src)
        elif src["type"] == "table" and table_counter in used_table_indices:
            filtered_sources.append(src)
```

---

## 8. PII 마스킹

### 백엔드 (API 응답 시점 마스킹)

**코드 위치**: `pii_masking.py`

| 함수 | 용도 |
|------|------|
| `mask_pii_text(text)` | 일반 텍스트에서 PII를 마스킹 문자로 치환 |
| `mask_pii_in_html(html)` | HTML의 텍스트 노드만 순회하며 PII 마스킹 |
| `mask_pii_in_data(value)` | 중첩 dict/list/str/int를 재귀적으로 마스킹 |

#### 탐지 패턴

| 유형 | 정규식 | 마스킹 방식 |
|------|--------|-------------|
| 주민등록번호 | `\d{6}[- ]?[1-4]\d{6}` | 앞2 + \*\*\* + 뒤2 |
| 외국인등록번호 | `\d{6}[- ]?[5-8]\d{6}` | 앞2 + \*\*\* + 뒤2 |
| 운전면허번호 | `\d{3}-\d{2}-\d{5}` | 앞2 + \*\*\* + 뒤2 |
| 여권번호 | `[A-Z]{1,2}\d{7,8}` | 앞2 + \*\*\* + 뒤2 |
| 차대번호 | `[A-HJ-NPR-Z0-9]{17}` | 앞2 + \*\*\* + 뒤2 |
| 신용카드번호 | `\d{4}-\d{4}-\d{4}-\d{4}` | 앞2 + \*\*\* + 뒤2 |
| 휴대전화 | `01[016789][ -]?\d{2,4}[ -]?\d{3,4}` | 앞3 + \*\*\* + 뒤2 |
| 유선전화 | `(02\|0[3-6][1-5]\|070\|050[2-8])...` | 앞3 + \*\*\* + 뒤2 |
| 이메일 | `...@...` | 로컬 앞1 + \*\*\* @ 도메인 |

### 프론트엔드 (PDF 캔버스 오버레이)

**코드 위치**: `web/src/utils/piiDetection.ts`

- PDF 렌더링 후 텍스트 span의 좌표를 기반으로 PII 영역을 **회색 사각형**으로 오버레이
- **라인 기반 검출**: 같은 y좌표의 span을 연결하여 텍스트 구성
- **Column gap 감지**: x 간격이 15px 초과 시 별도 세그먼트로 분리 (표 열 간섭 방지)
- **char-offset 매칭**: 전체 줄이 아닌 PII 매칭 범위만 마스킹

---

## 9. 파일 생명주기 (생성 / 삭제)

### 9.1 생성 시점

| 파일/디렉토리 | 생성 시점 | 생성 방법 |
|---|---|---|
| `pdf_upload_<uuid>/` | 세션 생성 시 | `tempfile.mkdtemp()` |
| `pdf_chroma_<uuid>/` | 세션 생성 시 | `tempfile.mkdtemp()` |
| `pdf_docchunks_<uuid>/` | 세션 생성 시 | `tempfile.mkdtemp()` |
| `{name}.html` | PDF 업로드 시 | `opendataloader_pdf.convert()` |
| `{name}.json` | PDF 업로드 시 | `opendataloader_pdf.convert()` |
| `{name}.md` | PDF 업로드 시 | `opendataloader_pdf.convert()` |
| `standard/{name}.html` | PDF 업로드 시 | `PDFProcessor.convert_standard()` |
| `chroma.sqlite3` | 표/텍스트 인덱싱 시 | ChromaDB 자동 생성 |
| `~/.pdftablesearch/fernet.key` | 첫 암호화 시 | `encryption.py` 자동 생성 |

### 9.2 삭제 시점

| 이벤트 | 삭제 대상 | 방법 | 코드 위치 |
|---|---|---|---|
| **세션 삭제** (`DELETE /api/sessions/{id}`) | `upload_dir`, `chroma_dir` | `shutil.rmtree()` | web_server.py L1237 |
| **서버 시작** (lifespan) | 이전 실행의 모든 `pdf_upload_*`, `pdf_chroma_*`, `pdf_docchunks_*` | glob + `shutil.rmtree()` | web_server.py L50 |
| **서버 재시작** | 메모리 `_sessions` 딕셔너리 | 프로세스 종료로 소멸 | — |
| **PDF 삭제** (`DELETE /api/pdfs/{name}`) | 해당 PDF 파일 + 변환 디렉토리 | `Path.unlink()` + `shutil.rmtree()` | web_server.py L1885 |
| **doc_chunks 재인덱싱** | 이전 `doc_chunks_dir` | `shutil.rmtree(old_dir)` | web_server.py L460 |
| **ChromaDB readonly 에러** | 해당 `chroma_dir` | `shutil.rmtree()` 후 재생성 | vectorstore.py L276 |

### 9.3 세션 데이터 (인메모리)

```python
_sessions: Dict[str, dict] = {}  # 서버 재시작 시 모두 손실!
```

세션에 저장되는 데이터:

| 키 | 타입 | 설명 |
|----|------|------|
| `upload_dir` | `str` | PDF 원본 + 변환 파일 임시 디렉토리 |
| `chroma_dir` | `str` | 표 ChromaDB 디렉토리 |
| `doc_chunks_dir` | `str` | 텍스트 청크 ChromaDB 디렉토리 |
| `pdfs` | `Dict[str, dict]` | PDF별 정보 (경로, 표 목록, 페이지 수, html_path, md_path) |
| `bm25_index` | `BM25Okapi` | BM25 키워드 검색 인덱스 |
| `bm25_chunks` | `list[str]` | BM25용 원본 텍스트 청크 |
| `bm25_metadatas` | `list[dict]` | BM25용 청크 메타데이터 |
| `document_chunks_ready` | `bool` | 텍스트 인덱싱 완료 여부 |
| `name` | `str` | 세션 이름 |
| `created_at` | `str` | 생성 시각 (ISO 8601) |
| `last_activity` | `str` | 마지막 활동 시각 |
| `total_pages` | `int` | 전체 페이지 수 |

---

## 10. 전체 데이터 흐름 요약

```
┌───────────────────────────────────────────────────────────────┐
│ 1. PDF 업로드                                                  │
│    POST /api/upload                                           │
│    ┌──────────────┐                                           │
│    │ hcs.pdf      │ ← 브라우저에서 업로드                       │
│    └──────┬───────┘                                           │
│           ↓                                                    │
│    ┌─────────────────────────────────────┐                    │
│    │ opendataloader-pdf (hybrid=docling)  │                    │
│    │ → hcs.html + hcs.json + hcs.md      │                    │
│    └──────┬──────────────────────────────┘                    │
│           ↓                                                    │
│    ┌──────────────────────────────┐                           │
│    │ HTML에서 <table> 추출         │ → 제목, 컨텍스트, HTML     │
│    │ JSON에서 bbox/페이지 추출     │ → 메타데이터               │
│    │ MD에서 제목 fallback 추출     │                           │
│    │ HTML↔JSON Jaccard 매칭       │ → 정확한 페이지+bbox       │
│    └──────┬───────────────────────┘                           │
│           ↓                                                    │
│    ┌──────────────────────────────┐                           │
│    │ PyMuPDF 보강                  │ → 누락 표 복구,            │
│    │ (fitz.find_tables)           │   hybrid bbox 우선 사용    │
│    └──────┬───────────────────────┘                           │
│           ↓                                                    │
│    ┌──────────────────────────────┐                           │
│    │ 다중페이지 표 감지            │ → 사용자 확인 팝업         │
│    └──────┬───────────────────────┘                           │
│           ↓                                                    │
│    ┌──────────────────────────────┐                           │
│    │ 임베딩 (BAAI/bge-m3)         │ → 1024차원 벡터            │
│    │ ChromaDB 저장 (표 + 텍스트)   │ → 암호화(OPTION)           │
│    │ BM25 인덱스 구축              │                           │
│    └──────────────────────────────┘                           │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│ 2. 문서 검색 (POST /api/unified-search)                        │
│    사용자: "자동차금융 성장세"                                   │
│           ↓                                                    │
│    ┌──────────────────────────────┐                           │
│    │ 표 Vector 검색 (k=10)        │ ← pdf_tables ChromaDB     │
│    │ 텍스트 Vector 검색 (k=8)     │ ← doc_chunks ChromaDB     │
│    │ 텍스트 BM25 검색 (k=8)       │ ← BM25Okapi 인메모리      │
│    └──────┬───────────────────────┘                           │
│           ↓ RRF Fusion (k=60)                                  │
│    ┌──────────────────────────────┐                           │
│    │ 상위 5개 텍스트 + 3개 표      │                           │
│    │ → PII 마스킹                 │                           │
│    │ → LLM 컨텍스트 구성          │                           │
│    └──────┬───────────────────────┘                           │
│           ↓                                                    │
│    ┌──────────────────────────────┐                           │
│    │ Ollama gpt-oss:120b          │                           │
│    │ → SSE 스트리밍 답변           │                           │
│    │ → 인라인 인용 [텍스트출처N]   │                           │
│    └──────┬───────────────────────┘                           │
│           ↓                                                    │
│    ┌──────────────────────────────┐                           │
│    │ 출처 파싱 + 필터링           │ → 사용된 출처만 칩으로 표시 │
│    └──────────────────────────────┘                           │
└───────────────────────────────────────────────────────────────┘
```

---

## 11. 주요 기술적 특징

| 특징 | 구현 |
|------|------|
| **하이브리드 표 감지** | opendataloader-pdf (OCR) + PyMuPDF (bbox) 이중 감지, hybrid bbox 우선 |
| **3단계 제목 추출** | HTML 헤더 → Markdown 헤더 → 없음 |
| **HTML↔JSON 매칭** | Jaccard 유사도 (임계값 0.3) |
| **다중페이지 표** | 위치 기반 감지 + 사용자 확인 팝업 (자동 병합 불가) |
| **RRF Fusion** | Vector + BM25 → Reciprocal Rank Fusion (k=60) |
| **로컬 임베딩** | BAAI/bge-m3 (1024차원, CPU, API 키 불필요) |
| **ChromaDB 암호화** | Fernet 대칭 암호화 (임베딩은 평문으로 미리 생성 후 page_content만 암호화) |
| **PII 마스킹** | 백엔드: regex + BS4 HTML 처리, 프론트엔드: PDF 캔버스 span 레벨 오버레이 |
| **SSE 스트리밍** | 검색 진행률 + LLM 토큰 단위 실시간 전송 |
| **세션 격리** | 각 세션마다 독립적인 ChromaDB + BM25 인덱스 |
| **PDF 좌표계** | 원점 왼쪽 하단, Y축 위쪽; `viewport.convertToViewportPoint()`로 변환 |
| **금융 문서 환각 방지** | "문서에 없는 내용은 추측하지 마세요" system prompt |

---

## 12. 관련 파일 인덱스

### 백엔드

| 파일 | 설명 |
|------|------|
| `pdftablesearch/web_server.py` | FastAPI 메인 서버 (API 라우트, 통합 검색, 업로드) |
| `pdftablesearch/loader/__init__.py` | `PDFProcessor` — PDF→HTML/JSON/MD 변환 + 표 추출 |
| `pdftablesearch/loader/html_parser.py` | HTML 표 추출, 정제, Markdown 변환 |
| `pdftablesearch/loader/json_parser.py` | JSON 메타데이터 (bbox, 페이지 번호) 파싱 |
| `pdftablesearch/loader/markdown_parser.py` | Markdown 표 추출, 제목/context 파싱 |
| `pdftablesearch/loader/matcher.py` | HTML↔JSON Jaccard 매칭 |
| `pdftablesearch/vectorstore.py` | ChromaDB 래퍼 (암호화/복호화 포함) |
| `pdftablesearch/local_embeddings.py` | BAAI/bge-m3 로컬 임베딩 |
| `pdftablesearch/encryption.py` | Fernet 암호화/복호화 |
| `pdftablesearch/pii_masking.py` | PII 탐지/마스킹 (텍스트 + HTML) |
| `pdftablesearch/hybrid_search.py` | RRF 하이브리드 검색 |
| `pdftablesearch/llm_client.py` | Ollama LLM 클라이언트 |
| `pdftablesearch/config.py` | 설정 관리 |

### 프론트엔드

| 파일 | 설명 |
|------|------|
| `web/src/components/UnifiedSearchView.tsx` | 통합 문서 검색 UI + 출처 팝업 |
| `web/src/components/DocumentViewer.tsx` | PDF 뷰어 + 표 오버레이 + PII 마스킹 |
| `web/src/utils/piiDetection.ts` | 프론트엔드 PII 라인 기반 검출 + PDF 캔버스 오버레이 |
| `web/src/api/client.ts` | API 클라이언트 (SSE 스트리밍) |
| `web/src/store/useAppStore.ts` | Zustand 글로벌 상태 관리 |
| `web/src/types/index.ts` | TypeScript 타입 정의 |
