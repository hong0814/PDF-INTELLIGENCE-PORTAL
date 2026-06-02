# PDF Intelligence Portal — 시스템 아키텍처

> 최종 수정: 2026-06-02

---

## 1. 비즈니스 시스템 아키텍처 (C4 Context)

```mermaid
graph TB
    subgraph "사용자"
        심사역["심사역<br/>기업금융심사"]
        리스크["리스크 분석가<br/>리스크 관리"]
        운영["운영담당자<br/>일반 문서 조회"]
    end

    subgraph "PDF Intelligence Portal"
        portal["PDF Intelligence Portal<br/>금융 문서 AI 분석 시스템<br/>LDAP 인증 · PII 마스킹"]
    end

    subgraph "외부 시스템"
        ldap["LDAP 서버<br/>기업 디렉토리<br/>인증"]
        ollama["Ollama Cloud<br/>gpt-oss:120b"]
        hybrid["Opendataloader-PDF<br/>docling-fast :5002"]
    end

    심사역 -->|PDF 업로드 / 심사 검색| portal
    리스크 -->|리스크 지표 검색 / 분석| portal
    운영 -->|문서 조회 / 번역| portal

    portal -->|LDAP Bind 인증| ldap
    portal -->|LLM 응답 생성 SSE| ollama
    portal -->|PDF 변환 HTML/JSON + OCR| hybrid

    style portal fill:#4A90D9,color:#fff,stroke:#2C5F8A
    style ldap fill:#E74C3C,color:#fff,stroke:#A93226
    style ollama fill:#9B59B6,color:#fff,stroke:#6C3483
    style hybrid fill:#E67E22,color:#fff,stroke:#A04000
```

---

## 2. 시스템 아키텍처 (C4 Container)

```mermaid
graph TB
    subgraph "Browser"
        react["React 19 + TypeScript<br/>Zustand · Tailwind v4<br/>pdf.js · react-markdown"]
    end

    subgraph "Application Server :8000"
        fastapi["FastAPI Python 3.11<br/>─────────<br/>web_server.py · auth.py<br/>table_utils.py · doc_processing.py<br/>인메모리 세션"]
    end

    subgraph "인증"
        ldap_srv["OpenLDAP :3890<br/>dc=pdfportal,dc=local"]
        jwt["JWT httpOnly Cookie<br/>HS256 서명"]
    end

    subgraph "Data Layer"
        weaviate["Weaviate Embedded<br/>─────────<br/>:8079 HTTP :50050 gRPC<br/>pdf_table_chunks<br/>doc_chunks<br/>Hybrid Search 지원"]
        bm25["BM25 인덱스<br/>한국어 토크나이징"]
        st["SentenceTransformer<br/>BAAI/bge-m3 1024차원"]
    end

    subgraph "Cloud"
        ollama_api["Ollama Cloud API<br/>gpt-oss:120b"]
    end

    react -->|HTTP / SSE| fastapi
    fastapi -->|LDAP Bind| ldap_srv
    fastapi -->|JWT 발급/검증| jwt
    fastapi -->|벡터 저장/검색| weaviate
    fastapi -->|키워드 검색| bm25
    fastapi -->|임베딩 생성| st
    fastapi -->|LLM API| ollama_api

    style react fill:#61DAFB,color:#000
    style fastapi fill:#009688,color:#fff
    style ldap_srv fill:#E74C3C,color:#fff
    style weaviate fill:#FF6B6B,color:#fff
    style st fill:#2ECC71,color:#fff
    style ollama_api fill:#9B59B6,color:#fff
```

---

## 3. 컴포넌트 아키텍처

```mermaid
graph TB
    subgraph "API Layer"
        ws["web_server.py<br/>API 엔드포인트 · 세션 관리"]
        auth["auth.py<br/>LDAP + JWT 인증"]
    end

    subgraph "검색 파이프라인"
        core["core.py<br/>검색 오케스트레이션"]
        search["search.py<br/>PDFTableSearch"]
        smart["smart_search.py<br/>LLM 표 선택"]
        hybrid["hybrid_search.py<br/>벡터+BM25+RRF"]
        reranker["reranker.py<br/>리랭킹"]
    end

    subgraph "문서 처리"
        loader["loader/<br/>PDF → HTML/JSON"]
        tu["table_utils.py<br/>표 감지/매칭/병합"]
        dp["doc_processing.py<br/>텍스트 분할"]
    end

    subgraph "AI / LLM"
        llm["llm_client.py<br/>Ollama API"]
        qa["table_qa.py<br/>표 Q&A"]
        trans["translation.py<br/>번역"]
    end

    subgraph "데이터 계층"
        wvs["vectorstores/<br/>WeaviateTableVectorStore"]
        emb["local_embeddings.py<br/>bge-m3"]
        pii["pii_masking.py<br/>PII 마스킹"]
    end

    subgraph "인프라"
        cfg["config.py<br/>LDAP · Weaviate · Auth 설정"]
    end

    ws --> auth
    ws --> core & smart & hybrid & qa & trans & tu
    core --> search & reranker
    search --> wvs
    wvs --> emb
    smart --> llm & search
    hybrid --> wvs
    reranker --> llm
    ws --> loader & dp & pii
    qa --> llm

    style ws fill:#009688,color:#fff
    style auth fill:#E74C3C,color:#fff
    style wvs fill:#FF6B6B,color:#fff
    style vs_factory fill:#FF6B6B,color:#fff
```

---

## 4. 데이터 플로우

### 4.1 PDF 업로드 & 인덱싱

```mermaid
flowchart TD
    A["PDF 파일 업로드"] --> B["Opendataloader-PDF<br/>docling-fast 변환"]
    B --> C["HTML 파일 생성<br/>(페이지 구분자 포함)"]
    B --> D["JSON 메타데이터<br/>bbox · 페이지 번호"]

    C --> E["HTML 표 추출"]
    D --> F["JSON ↔ HTML 매칭"]
    E --> F

    F --> G["PyMuPDF 표 감지<br/>find_tables()"]
    G --> H["표 융합<br/>PyMuPDF ↔ Hybrid HTML<br/>inner table · 다중페이지 체인"]

    H --> I["표 HTML → 임베딩<br/>bge-m3 1024차원"]
    I --> J["Weaviate 저장<br/>pdf_table_chunks"]

    C --> K["표 제거 + 페이지 분할"]
    K --> L["텍스트 청킹<br/>1000자 200 오버랩"]
    L --> M["Weaviate 저장<br/>doc_chunks"]
    L --> N["BM25 인덱스 구축<br/>한국어 토크나이징"]

    style A fill:#4A90D9,color:#fff
    style J fill:#FF6B6B,color:#fff
    style M fill:#FF6B6B,color:#fff
```

### 4.2 통합 문서 검색

```mermaid
flowchart TD
    Q["사용자 쿼리"] --> V["Weaviate pdf_table_chunks<br/>Hybrid Search"]
    Q --> T["Weaviate doc_chunks<br/>Hybrid Search"]
    Q --> B["BM25 키워드 검색"]

    V --> RRF["RRF Fusion"]
    T --> RRF
    B --> RRF

    RRF --> PII["PII 마스킹<br/>주민번호 · 계좌번호 · 전화번호"]
    PII --> CTX["컨텍스트 구성<br/>출처 마커 부착"]
    CTX --> LLM["Ollama gpt-oss:120b<br/>SSE 스트리밍"]

    LLM --> ANS["AI 답변 + 출처<br/>텍스트출처N · 표출처N"]

    style Q fill:#4A90D9,color:#fff
    style RRF fill:#E67E22,color:#fff
    style LLM fill:#9B59B6,color:#fff
    style ANS fill:#2ECC71,color:#fff
```

---

## 5. 시퀀스 다이어그램

### 5.1 LDAP 인증

```mermaid
sequenceDiagram
    actor User
    participant FE as React
    participant API as FastAPI
    participant LDAP as OpenLDAP

    User->>FE: 로그인 (사번/비밀번호)
    FE->>API: POST /api/auth/login
    activate API

    API->>LDAP: LDAP Bind (관리자)
    LDAP-->>API: Bind 성공

    API->>LDAP: LDAP Search (uid=사번)
    LDAP-->>API: 사용자 DN + 속성

    API->>LDAP: LDAP Bind (사용자 DN + 비밀번호)
    LDAP-->>API: 인증 성공

    API->>API: JWT 생성 (user_id, name, role)
    API-->>FE: Set-Cookie: auth_token=JWT (httpOnly)
    deactivate API
    FE-->>User: 로그인 완료 → 메인 화면
```

### 5.2 PDF 업로드 & 표 추출

```mermaid
sequenceDiagram
    actor User
    participant FE as React
    participant API as FastAPI
    participant ODL as Opendataloader-PDF
    participant PyMuPDF as PyMuPDF
    participant WV as Weaviate
    participant BM25 as BM25 Index

    User->>FE: PDF 파일 드래그앤드롭
    FE->>API: POST /api/upload (multipart)
    activate API

    API->>ODL: PDF → HTML/JSON 변환
    activate ODL
    ODL-->>API: HTML + JSON 메타데이터
    deactivate ODL

    API->>API: HTML에서 표 추출 + JSON 매칭
    API->>PyMuPDF: find_tables() 표 감지
    PyMuPDF-->>API: 표 bbox + 셀 데이터

    API->>API: 표 융합 + 다중페이지 체인 감지

    loop 각 표
        API->>WV: 임베딩 저장 (pdf_table_chunks)
    end

    API->>API: 텍스트 청킹
    loop 각 청크
        API->>WV: 임베딩 저장 (doc_chunks)
    end
    API->>BM25: BM25 인덱스 구축

    API-->>FE: 업로드 완료 (표 수, 페이지 수)
    deactivate API
    FE-->>User: 업로드 완료 표시
```

### 5.3 통합 문서 검색

```mermaid
sequenceDiagram
    actor User
    participant FE as React
    participant API as FastAPI
    participant WV as Weaviate
    participant BM25 as BM25
    participant PII as PII Masking
    participant LLM as Ollama Cloud

    User->>FE: "재무상태표 요약" 검색
    FE->>API: POST /api/unified-search (SSE)
    activate API

    par 병렬 검색
        API->>WV: pdf_table_chunks hybrid search
        API->>WV: doc_chunks hybrid search
        API->>BM25: 키워드 검색
    end

    API->>API: RRF Fusion 결과 융합

    API->>PII: 표 HTML & 텍스트 마스킹
    API->>API: 컨텍스트 구성

    API->>LLM: 컨텍스트 + 쿼리 전달
    activate LLM
    loop 토큰 스트리밍
        LLM-->>API: 토큰 조각
        API-->>FE: SSE: answer 토큰
    end
    LLM-->>API: 응답 완료
    deactivate LLM

    API->>API: table_id 매칭<br/>(fitz_id + hybrid_id)
    API-->>FE: SSE: result (출처 + 관련표)
    deactivate API

    FE-->>User: AI 답변 + 출처 칩 렌더링

    User->>FE: 출처 칩 클릭
    FE->>API: GET /api/documents/page-image
    API-->>FE: PDF 페이지 이미지 + bbox
    FE-->>User: 하이라이트된 출처 팝업
```

### 5.4 문서 보기

```mermaid
sequenceDiagram
    actor User
    participant FE as React
    participant PDFjs as pdf.js
    participant API as FastAPI

    User->>FE: 문서 보기 탭
    FE->>API: GET /api/documents/pdf
    API-->>FE: PDF 파일
    FE->>PDFjs: 페이지 렌더링

    FE->>API: GET /api/documents/tables
    API-->>FE: 표 목록 (table_id · page · bbox)

    FE->>FE: 표 bbox 오버레이 렌더링

    User->>FE: 표 클릭
    FE->>API: GET /api/documents/html?table_id=...
    API-->>FE: 표 HTML (PII 마스킹)
    FE-->>User: 표 상세 + CSV 다운로드
```

### 5.5 표 Q&A

```mermaid
sequenceDiagram
    actor User
    participant FE as React
    participant API as FastAPI
    participant LLM as Ollama Cloud

    User->>FE: 표 카드에서 질문 입력
    FE->>API: POST /api/qa (SSE)
    activate API

    API->>API: table_html PII 마스킹
    API->>LLM: 표 HTML + 질문 전달
    activate LLM

    loop 토큰 스트리밍
        LLM-->>API: 토큰 조각
        API-->>FE: SSE: 토큰
    end
    LLM-->>API: 완료
    deactivate LLM

    API-->>FE: SSE: done
    deactivate API
    FE-->>User: 마크다운 렌더링된 답변
```

---

## 6. API 엔드포인트 맵

```mermaid
graph LR
    subgraph "Auth"
        A1["POST /api/auth/login"]
        A2["POST /api/auth/logout"]
    end

    subgraph "Session"
        S1["GET /api/sessions"]
        S2["POST /api/sessions"]
        S3["GET /api/sessions/:id"]
        S4["PUT /api/sessions/:id"]
        S5["DELETE /api/sessions/:id"]
    end

    subgraph "Document"
        D1["POST /api/upload"]
        D2["GET /api/documents/pdf"]
        D3["GET /api/documents/page-image"]
        D4["GET /api/documents/tables"]
        D5["GET /api/documents/html"]
    end

    subgraph "Search"
        R1["POST /api/search"]
        R2["POST /api/smart-search"]
        R3["POST /api/unified-search"]
        R4["POST /api/unified-followup"]
    end

    subgraph "AI"
        Q1["POST /api/qa"]
        Q2["POST /api/ask-document"]
    end

    subgraph "Translation"
        T1["POST /api/translate/html-pages"]
        T2["POST /api/translate/document"]
    end

    subgraph "Table"
        B1["POST /api/table/transpose"]
        B2["POST /api/table/calculate"]
    end

    subgraph "Utility"
        U1["GET /api/health"]
    end
```

---

## 7. 핵심 설계 결정

### 7.1 벡터 DB (Weaviate)

```
Weaviate Embedded :8079/:50050
  ├── PdfTables 컬렉션 (표 임베딩)
  └── DocChunks 컬렉션 (텍스트 청크 임베딩)
      Hybrid Search 지원 (벡터 + 키워드)
```

`vectorstores/weaviate_store.py`의 `WeaviateTableVectorStore`가 `VectorStoreBackend` 프로토콜을 구현합니다.

### 7.2 table_id 이중 매칭

```
Weaviate에 저장된 표 ID:  table_7_910  (hybrid/opendataloader-pdf 포맷)
세션에 저장된 표 ID:      fitz_p1_0    (PyMuPDF 매칭 후 생성)

매칭 로직:
  1. table_id 직접 비교
  2. hybrid_table_id 폴백 비교 (table_utils.py에서 보존)
```

### 7.3 좌표계 (bbox)

```
PDF 좌표계 (docling, opendataloader-pdf)    PyMuPDF 좌표계 (fitz)
┌─────────────────────┐                     ┌─────────────────────┐
│ (0, max_y) ←→ (max) │                     │ (0,0)       → (max) │
│        ↑ y↑          │                     │        ↓ y↓          │
│ 원점: 왼쪽 하단       │                     │ 원점: 왼쪽 상단       │
└─────────────────────┘                     └─────────────────────┘

docling/opendataloader-pdf bbox: 이미 PDF coords → 변환 금지
PyMuPDF (fitz) bbox: PDF coords로 변환 필요
하이라이트 오버레이: 항상 PyMuPDF(fitz) bbox 우선 사용
```

### 7.4 표 감지 융합 전략

```
PyMuPDF find_tables()  +  Hybrid (opendataloader-pdf)
        ↓                           ↓
    outer tables              HTML tables
        ↓                           ↓
    ┌─────────────────────────────────┐
    │ 1. PyMuPDF outer → HTML 매칭    │
    │    (텍스트 유사도 + y좌표 오버랩) │
    │ 2. 매칭 성공 → hybrid HTML 사용  │
    │    bbox는 hybrid 것 우선         │
    │ 3. 매칭 실패 → PyMuPDF HTML 폴백 │
    │ 4. Hybrid 전용 표 → fallback 추가│
    │ 5. 다중페이지 표 체인 감지        │
    └─────────────────────────────────┘
```

### 7.5 PII 마스킹 적용 범위

- **RAG 검색 결과**: 표 HTML, 텍스트 청크 모두 마스킹
- **문서 보기**: 표 HTML 렌더링 시 마스킹
- **출처 팝업**: PDF 하이라이트 텍스트 마스킹
- **Q&A**: 사용자 질문 히스토리 정제

### 7.6 인증 플로우

```
1. POST /api/auth/login {user_id, password}
   → LDAP Bind (관리자 DN) → LDAP Search (uid) → LDAP Bind (사용자 DN)
   → JWT 생성 (user_id, name, role) → httpOnly Cookie Set

2. 이후 모든 API 요청
   → Cookie에서 JWT 추출 → 검증 → user_id 주입

3. POST /api/auth/logout
   → Cookie 삭제
```

### 7.7 세션 관리

- **저장소**: 인메모리 `_sessions` 딕셔너리 (서버 재시작 시 손실)
- **격리**: 각 세션 = 독립 임시 디렉토리 (업로드, Weaviate, BM25)
- **정리**: 세션 삭제 시 임시 디렉토리 `shutil.rmtree()`
