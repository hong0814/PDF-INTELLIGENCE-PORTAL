# PDFTableSearch → Enterprise Finance Review Agent

## Implementation Plan v3.0 (Final)

> **Target**: React (Vite + Tailwind) + Python FastAPI backend  
> **Reference UI**: `web/demo-mockup/index.html` (807 lines)  
> **Constraints**: Streamlit untouched / Share & Report buttons EXCLUDED / Single-user in-memory session  
> **Tech Stack (LOCKED)**: Zustand (state), LangChain (RAG), opendataloadpdf HTML (document viewer), Lucide (icons), DOMPurify (sanitization)

---

## 1. Executive Summary

Transform the current single-function (table search) web app into a multi-tab workflow (Main → Document Viewer → Table Search → Q&A) matching the mockup pixel-for-pixel. All technology decisions are final. All mockup features accounted for (except Share/Report per user request).

---

## 2. Current State Audit

### 2.1 What Already Exists (DO NOT rebuild)

| Component | File | Status |
|-----------|------|--------|
| Zustand store | `store/useAppStore.ts` | ✅ Working — tab switching, session, PDFs, search results |
| Tab bar | `components/TabBar.tsx` | ✅ Working — 4 tabs (main/document/search/qa) |
| Session header | `components/SessionHeader.tsx` | ✅ Working — session name, PDF list |
| Global sidebar | `components/Sidebar.tsx` | ✅ Partial — has upload, search history; missing session history list, usage stats, version footer |
| Main screen | `components/MainScreen.tsx` | ✅ Working — dropzone + feature cards |
| Search bar | `components/SearchBar.tsx` | ✅ Working — basic search + smart search |
| Search results | `components/SearchResults.tsx` | ✅ Working — renders table cards |
| API client | `api/client.ts` | ✅ Working — upload, search, smart-search, QA streaming, listPdfs, deletePdf |
| Backend sessions | `web_server.py` | ✅ Working — CRUD sessions, in-memory `_sessions` dict |
| Backend upload | `web_server.py` | ✅ Working — saves `html_path`, `page_count`, `tables` per PDF |
| Backend document HTML | `web_server.py` | ✅ Working — `GET /api/documents/{pdf_name}/html` returns full HTML |
| Backend search | `web_server.py` | ✅ Working — `/api/search`, `/api/smart-search` (SSE) |
| Backend table QA | `web_server.py` | ✅ Working — `POST /api/qa` (SSE streaming) |
| PDF loader | `loader/__init__.py` | ✅ Working — opendataloadpdf `convert(format="html, json")`, outputs full-document HTML |
| Health check | `web_server.py` | ✅ Working — `GET /api/health` |

### 2.2 What's Missing vs Mockup

| Feature | Mockup Location | Current Status |
|---------|-----------------|----------------|
| Global Sidebar: session history list | Lines 78-138 | ❌ No session list, no usage badges (표검색 3회, Q&A 12회) |
| Global Sidebar: version footer | Line 143 | ❌ Missing |
| Global Sidebar: "새 세션 만들기" button | Line 73 | ❌ Not wired (needs POST /api/sessions → switch session) |
| SessionHeader: PDF badges with table counts | Lines 164-169 | ❌ Current shows generic PDF count, not per-PDF badges |
| SessionHeader: "PDF 추가" dashed button | Line 172 | ❌ Missing (or not styled) |
| Document Viewer tab (entire) | Lines 274-447 | ❌ Placeholder only — needs PageSidebar + continuous scroll + table overlays |
| PageSidebar (inner, light bg) | Lines 281-362 | ❌ Not implemented — document list, page jump, table list with tags |
| DocumentViewer continuous scroll | Lines 365-446 | ❌ Not implemented — render full HTML with page dividers, table hover actions |
| TableInDocument hover actions | Lines 380-401 | ❌ Not implemented — group-hover copy/Excel buttons on tables in document |
| Search: "HOT" badge + indexing count | Lines 457-458 | ❌ Missing |
| Search: search time display | Lines 472-474 | ⚠️ `searchTime` in store but may not be displayed |
| Search: table tags (재무제표/손익계산서/리스크/담보) | Lines 487, 316-317, 326 | ❌ No tag system — needs backend table_type field + frontend TableTag component |
| Search: "Smart 선택" badge | Line 488 | ❌ Missing on search result cards |
| Search: relevance score display (97.3%) | Lines 493-494 | ❌ Missing on cards |
| Search: TrendBadge (+22.6% 성장, -4.2% 감소) | Lines 512-517 | ❌ Missing — needs LLM analysis or rule-based trend extraction |
| Search: inline QA area ("이 표에 질문하기") | Lines 521, 526-612 | ❌ Missing — expand/collapse QA chat within search result card |
| Search: recommended question chips | Lines 533-537 | ❌ Missing — "3년 평균 성장률은?", "가로축 변경" etc. |
| Search: transpose answer in card | Lines 586-611 | ❌ Missing — needs `POST /api/table-transpose/:tableId` |
| Search: calculation answer in card | Lines 549-574 | ❌ Missing — needs `POST /api/table-calculate` |
| Q&A tab (entire) | Lines 657-753 | ❌ Placeholder only — needs QAPanel, ChatBubble, source chips, recommended questions |
| Q&A: "문서 이해 완료" green dot badge | Line 668 | ❌ Missing |
| Q&A: recommended questions | Lines 675-677 | ❌ Missing — "부채비율 추이?", "PF대출 만기?" |
| Q&A: AI greeting message | Lines 681-687 | ❌ Missing |
| Q&A: source-chip citations | Lines 718-722 | ❌ Missing — "p.15 대차대조표" clickable chips |
| Q&A: loading spinner state | Line 736 | ❌ Missing — "문서를 검색하고 계산 중..." |
| Q&A: disclaimer footer | Line 750 | ❌ Missing — "AI 답변은 문서 기반이지만..." |
| Backend: table tags/type | — | ❌ No `table_type` field in metadata |
| Backend: document tables list API | — | ❌ No `GET /api/documents/{pdf_name}/tables` |
| Backend: table transpose API | — | ❌ No `POST /api/table-transpose/:tableId` |
| Backend: table calculate API | — | ❌ No `POST /api/table-calculate` |
| Backend: document RAG (ask-document) | — | ❌ No `POST /api/ask-document` |
| Backend: document chunking pipeline | — | ❌ No ChromaDB `document_chunks` collection |

### 2.3 Excluded per User Request

- **"공유" (Share) button** — mockup line 179, EXCLUDED
- **"보고서" (Report) button** — mockup line 182, EXCLUDED
- **File attachment (paperclip in Q&A)** — mockup line 746, EXCLUDED (simplified)

---

## 3. Technology Decisions (ALL FINAL)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| State management | **Zustand** | Already installed and in use |
| RAG framework | **LangChain** | Already in use for table search; extend for document RAG |
| PDF→HTML | **opendataloadpdf** | Already outputs full-document HTML; no additional PDF library needed |
| HTML sanitization | **DOMPurify** | Industry standard, lightweight, npm package |
| Icons | **Lucide React** | Already using inline SVGs; migrate to Lucide for consistency, tree-shakeable |
| Table operations | **pandas (backend)** | DataFrame transpose + calculation; already a transitive dependency |
| Vector store | **ChromaDB** | Already in use; add separate `document_chunks` collection |
| CSS framework | **Tailwind CSS** | Already in use |
| Font | **Pretendard** | Specified in mockup CDN link |
| Session persistence | **In-memory dict** | Single-user; no DB needed for now |
| Document chunking | **LangChain RecursiveCharacterTextSplitter** | Standard, configurable chunk size/overlap |
| Streaming | **SSE (Server-Sent Events)** | Already used for smart-search and QA |
| CSV export | **Frontend-only** | Blob + BOM prefix (as in mockup script) |

---

## 4. Backend API Changes

### 4.1 New Endpoints

| # | Method | Endpoint | Input | Output | Purpose |
|---|--------|----------|-------|--------|---------|
| 1 | `GET` | `/api/documents/{pdf_name}/tables` | `X-Session-ID` header | `{ tables: [{ table_id, title, page_number, table_type, bounding_box }] }` | List all tables for a document with tags and page info |
| 2 | `POST` | `/api/table-transpose/{pdf_name}/{table_id}` | `X-Session-ID` header | `{ html: "..." }` | Transpose table rows↔columns, return new HTML |
| 3 | `POST` | `/api/table-calculate` | `{ question, pdf_name, table_id, X-Session-ID }` | SSE stream of tokens | Calculate derived metrics from table data |
| 4 | `POST` | `/api/ask-document` | `{ question, X-Session-ID }` | SSE stream of tokens + source citations | Document-wide RAG Q&A |

### 4.2 Modified Endpoints

| Endpoint | Change |
|----------|--------|
| `POST /api/upload` | Store `table_type` field per table (classify as 재무제표/손익계산서/리스크/담보/기타) |
| `GET /api/sessions` | Include `search_count`, `qa_count` in session brief serialization |
| `GET /api/sessions/{id}` | Same — include usage stats |

### 4.3 Data Model Additions

```python
# web_server.py — extend session["pdfs"][name] dict:
{
    "path": str,
    "table_count": int,
    "html_path": Optional[str],
    "page_count": int,
    "tables": [
        {
            "table_id": str,
            "title": Optional[str],
            "page_number": int,
            "table_type": str,  # NEW: "재무제표"|"손익계산서"|"리스크"|"담보"|"기타"
            "bounding_box": List[float],
            "table_html": str,
            "table_markdown": str,
        }
    ],
}
# Extend session dict:
{
    ...existing fields...,
    "search_count": int,   # NEW: increment on each search
    "qa_count": int,       # NEW: increment on each QA
    "document_chunks_ready": bool,  # NEW: True after chunking completes
}
```

### 4.4 Table Type Classification Logic

Heuristic classification based on table title/content keywords:
- Title contains "매출", "재무", "대차대조표", "재무상태표" → `"재무제표"`
- Title contains "손익", "영업이익", "분기별" → `"손익계산서"`
- Title contains "리스크", "위험", "PF", "부실" → `"리스크"`
- Title contains "담보", "보증", "평가" → `"담보"`
- Default → `"기타"`

Implementation: Single function `_classify_table_type(title: str, context: str) -> str` in `web_server.py`.

### 4.5 Document Chunking Pipeline (for ask-document)

```
On upload (or lazy on first ask-document):
  1. Read full HTML from html_path
  2. Strip HTML tags → plain text
  3. LangChain RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
  4. Embed chunks with SentenceTransformerEmbeddings (same as table embeddings)
  5. Store in ChromaDB collection "document_chunks_{session_id}"
  6. Set session["document_chunks_ready"] = True
```

On ask-document request:
```
  1. Embed question
  2. Search document_chunks collection → top-5 similar chunks
  3. Build LLM prompt with system persona (AI 심사역) + chunks + question
  4. Stream response with source metadata (page numbers from chunk metadata)
```

---

## 5. Frontend Component Architecture

### 5.1 Component Tree (Final)

```
App
├── Sidebar (global, dark, w-[280px])                    ← MODIFY: add session history, stats, version
│   ├── Logo + Title
│   ├── "새 세션 만들기" button                          ← NEW: create session + switch
│   ├── Session history list                              ← NEW: active/inactive states, usage badges
│   └── Version footer                                    ← NEW
├── Main content area (flex-1)
│   ├── SessionHeader                                     ← MODIFY: per-PDF badges, "PDF 추가" button
│   ├── TabBar                                            ← EXISTS
│   └── Content (switch by activeTab)
│       ├── Tab: main → MainScreen                        ← EXISTS
│       ├── Tab: document → DocumentTab                   ← NEW
│       │   ├── PageSidebar (inner, light, w-56)          ← NEW
│       │   │   ├── Document list (with selection)
│       │   │   ├── Page jump links (with table count)
│       │   │   └── Table list (with tags + page refs)
│       │   └── DocumentViewer (scroll area)              ← NEW
│       │       ├── Page divider overlays ("— N페이지 —")
│       │       ├── Rendered HTML (DOMPurify sanitized)
│       │       └── TableInDocument (hover actions)        ← NEW
│       │           ├── Copy button
│       │           └── Excel/CSV download button
│       ├── Tab: search → SearchTab                       ← MODIFY existing
│       │   ├── Search header (title + HOT badge + index count)
│       │   ├── SearchBar                                 ← EXISTS, MODIFY: style tweaks
│       │   ├── Search time display
│       │   ├── SearchResults                             ← MODIFY: add tags, badges, score
│       │   │   └── TableCard                             ← MODIFY heavily
│       │   │       ├── Header (icon + title + tags + score + "Smart 선택")
│       │   │       ├── Table HTML render
│       │   │       ├── TrendBadge row                    ← NEW
│       │   │       ├── Action buttons (Excel/QA/Copy)
│       │   │       └── Inline QA area (expandable)      ← NEW
│       │   │           ├── RecommendedQuestions chips    ← NEW
│       │   │           ├── QA input
│       │   │           └── QA answer (ChatBubble style)
│       │   ├── Empty state ("PDF를 업로드하고 검색어를 입력하세요")
│       │   └── Loading state (spinner)
│       └── Tab: qa → QAPanel                             ← NEW
│           ├── Header bar (AI 심사역 + "문서 이해 완료" + 초기화)
│           ├── Message list (scroll area)
│           │   ├── Recommended questions chips
│           │   ├── ChatBubble (AI greeting)
│           │   ├── ChatBubble (user question)
│           │   ├── ChatBubble (AI answer + source-chips)
│           │   └── ChatBubble (loading spinner)
│           ├── Input bar (textarea + send button)
│           └── Disclaimer footer
```

### 5.2 New Components

| Component | File | Props | Description |
|-----------|------|-------|-------------|
| `DocumentTab` | `components/DocumentTab.tsx` | none (reads store) | Container: PageSidebar + DocumentViewer side by side |
| `PageSidebar` | `components/PageSidebar.tsx` | `pdfName, tables, pages, onSelectPage, onSelectTable` | Inner light sidebar for document tab |
| `DocumentViewer` | `components/DocumentViewer.tsx` | `htmlContent, tables` | Continuous scroll renderer with page dividers |
| `TableInDocument` | `components/TableInDocument.tsx` | `tableHtml, tableTitle` | Wrapped table with group-hover copy/Excel buttons |
| `QAPanel` | `components/QAPanel.tsx` | none (reads store) | Full Q&A chat interface |
| `ChatBubble` | `components/ChatBubble.tsx` | `role, content, sources?, isLoading?` | AI/user message bubble |
| `TrendBadge` | `components/TrendBadge.tsx` | `label, value, direction: 'up'|'down'` | Green up / red down trend pill |
| `TableTag` | `components/TableTag.tsx` | `type: string` | Colored tag: 재무제표(blue), 손익계산서(gray), 리스크(red), 담보(green) |
| `RecommendedQuestions` | `components/RecommendedQuestions.tsx` | `questions, onSelect` | Clickable question chips |
| `SourceChip` | `components/SourceChip.tsx` | `page, title, onClick?` | Blue pill citing source page |

### 5.3 Modified Components

| Component | Changes |
|-----------|---------|
| `Sidebar` | Add session history list, usage stats badges (표검색 N회, Q&A N회), version footer, wire "새 세션 만들기" |
| `SessionHeader` | Per-PDF badges showing name + table count, dashed "PDF 추가" upload button |
| `SearchResults` | Pass table tags, relevance score, trend data to cards; add empty/loading states |
| `TableCard` (or inline in SearchResults) | Add tag, score, "Smart 선택" badge, TrendBadge row, inline QA area, recommended questions |
| `SearchBar` | Minor style tweaks to match mockup (card-elevated wrapper, sparkle icon) |
| `useAppStore` | Add: `sessions: SessionSummary[]`, `documentHtml: string`, `documentTables: TableMeta[]`, `qaMessages: QAMessage[]`, `currentDocumentPdf: string`, actions for all new data |

### 5.4 Zustand Store Extensions

```typescript
// store/useAppStore.ts — additions

interface SessionSummary {
  sessionId: string;
  name: string;
  createdAt: string;
  pdfCount: number;
  totalTables: number;
  searchCount: number;
  qaCount: number;
}

interface TableMeta {
  tableId: string;
  title: string | null;
  pageNumber: number;
  tableType: string; // "재무제표" | "손익계산서" | "리스크" | "담보" | "기타"
}

interface QAMessage {
  id: string;
  role: 'user' | 'ai';
  content: string;
  sources?: { page: number; title: string }[];
  isLoading?: boolean;
}

// New state fields:
sessions: SessionSummary[];
documentHtml: string | null;
documentTables: TableMeta[];
currentDocumentPdf: string | null;
qaMessages: QAMessage[];

// New actions:
loadSessions: () => Promise<void>;
createSession: (name?: string) => Promise<void>;
switchSession: (sessionId: string) => Promise<void>;
loadDocumentHtml: (pdfName: string) => Promise<void>;
loadDocumentTables: (pdfName: string) => Promise<void>;
askDocument: (question: string) => Promise<void>;
askTableQuestion: (pdfName: string, tableId: string, question: string) => Promise<string>;
transposeTable: (pdfName: string, tableId: string) => Promise<string>;
clearQA: () => void;
addQAMessage: (msg: QAMessage) => void;
updateQAMessage: (id: string, updates: Partial<QAMessage>) => void;
```

### 5.5 API Client Additions

```typescript
// api/client.ts — new functions

export async function listSessions(): Promise<{ sessions: SessionSummary[] }>;
export async function createSession(name?: string): Promise<{ session_id: string; name: string }>;
export async function getDocumentHtml(pdfName: string, sessionId: string): Promise<string>;
export async function getDocumentTables(pdfName: string, sessionId: string): Promise<{ tables: TableMeta[] }>;
export async function transposeTable(pdfName: string, tableId: string, sessionId: string): Promise<{ html: string }>;
export async function askDocument(question: string, sessionId: string, onToken: (t: string) => void, onSources?: (s: any[]) => void): Promise<void>;
```

---

## 6. Execution Phases

### Phase 0: Pre-flight (Spike Resolution) — 0h

All spike questions are RESOLVED:

| Question | Answer | Evidence |
|----------|--------|----------|
| Can opendataloadpdf output full HTML? | YES | `loader/__init__.py` line 89: `format="html, json"`, single HTML file per PDF |
| Does backend already store HTML path? | YES | `web_server.py` line 296: `session["pdfs"][filename]["html_path"]` |
| Does document HTML endpoint exist? | YES | `web_server.py` line 203-215: `GET /api/documents/{pdf_name}/html` |
| Can we get per-table metadata? | YES | `web_server.py` lines 298-301: tables array stored per PDF |

**Phase 0 is COMPLETE. No work needed.**

---

### Phase 1: Foundation Upgrades — 8h

> Prerequisites: None. All infrastructure exists.

| # | Task | Files | Specific Changes | Success Criteria | Time |
|---|------|-------|-------------------|------------------|------|
| 1.1 | Backend: table type classification | `web_server.py` | Add `_classify_table_type(title, context) -> str` function. Call it during upload when storing `tables` array. Add `table_type` field to each table dict. | Upload returns tables with `table_type` field; manual curl verification | 1.5h |
| 1.2 | Backend: document tables API | `web_server.py` | New `GET /api/documents/{pdf_name}/tables` endpoint. Return `{ tables: [{ table_id, title, page_number, table_type, bounding_box }] }` from `session["pdfs"][name]["tables"]`. | `curl /api/documents/X/tables` returns table list with tags | 1h |
| 1.3 | Backend: session usage stats | `web_server.py` | Modify `_serialize_session_brief` to include `search_count` and `qa_count`. Already incremented in search/qa handlers — just expose them. | `GET /api/sessions` returns `search_count`, `qa_count` per session | 0.5h |
| 1.4 | Frontend: session history in Sidebar | `components/Sidebar.tsx`, `store/useAppStore.ts`, `api/client.ts` | Add `listSessions()`, `createSession()` to API client. Add `sessions`, `loadSessions`, `createSession`, `switchSession` to store. Render session list in Sidebar with active/inactive states, usage badges. Add "새 세션 만들기" button. Add version footer. | Sidebar shows session history, clicking switches session, "새 세션" creates and switches | 2h |
| 1.5 | Frontend: SessionHeader PDF badges | `components/SessionHeader.tsx` | Show per-PDF pill badges: PDF icon + name + table count (green). Add dashed "PDF 추가" button with upload handler. | Header shows individual PDF pills with table counts matching mockup | 1.5h |
| 1.6 | Frontend: Lucide icons setup | `web/package.json`, `web/src/App.tsx` (and others) | `npm install lucide-react`. Replace all inline SVGs with Lucide components throughout existing code. Icon mapping: `ph-house` → `Home`, `ph-file-text` → `FileText`, `ph-table` → `Table`, `ph-chat-circle-dots` → `MessageCircle`, `ph-magnifying-glass` → `Search`, `ph-sparkle` → `Sparkles`, `ph-cloud-arrow-up` → `CloudUpload`, etc. | All icons render correctly, no inline SVGs remain | 1.5h |

---

### Phase 2: Document Viewer — 16h

> Prerequisites: Phase 1 complete (table types, document tables API)

| # | Task | Files | Specific Changes | Success Criteria | Time |
|---|------|-------|-------------------|------------------|------|
| 2.1 | Frontend: DocumentTab container | `components/DocumentTab.tsx` (NEW) | Create container layout: `flex gap-4`. Left: `PageSidebar` (w-56, light bg). Right: `DocumentViewer` (flex-1, scroll). Reads `currentDocumentPdf` from store. If null, shows empty state "PDF를 선택하세요". Auto-selects first PDF if only one exists. | Tab renders two-column layout matching mockup proportions | 1h |
| 2.2 | Frontend: PageSidebar component | `components/PageSidebar.tsx` (NEW) | Three sections: (1) Document list — clickable items, active item has blue border/bg. (2) Page jump links — anchor links to `#page-N`, highlight pages with tables. (3) Table list — grouped by PDF, each entry shows title + page + TableTag. Scroll if overflow. | All three sections render, clicking page scrolls to it, clicking table scrolls to it | 3h |
| 2.3 | Frontend: TableTag component | `components/TableTag.tsx` (NEW) | Small colored pill: 재무제표 → `bg-[#dbeafe] text-[#2563eb]`, 손익계산서 → `bg-gray-100 text-gray-600`, 리스크 → `bg-[#fef2f2] text-[#ef4444]`, 담보 → `bg-[#f0fdf4] text-[#16a34a]`, 기타 → `bg-gray-50 text-gray-500`. | Tags render with correct colors per type | 0.5h |
| 2.4 | Frontend: DocumentViewer component | `components/DocumentViewer.tsx` (NEW) | Fetch HTML via `getDocumentHtml(pdfName, sessionId)`. Sanitize with DOMPurify. Parse HTML to insert page divider overlays at page boundaries (use table metadata `page_number` to estimate). Render with `dangerouslySetInnerHTML` inside a styled container (`max-w-[700px] mx-auto`). Detect `<table>` elements in the HTML and wrap them with `TableInDocument` overlay behavior. | Full document renders as continuous scroll, page dividers visible, tables have hover actions | 4h |
| 2.5 | Frontend: TableInDocument component | `components/TableInDocument.tsx` (NEW) | Wrapper: `relative group`. On hover, show floating action bar: table title label + Copy button + Excel/CSV button. Copy: extract table text with tab-separated values → clipboard. Excel: generate CSV with BOM prefix → download. Table itself gets `table-highlight` border on hover. | Hovering a table in document view shows copy/Excel buttons; both functions work | 2h |
| 2.6 | Frontend: DOMPurify sanitization utility | `utils/sanitizeHtml.ts` (NEW) | `npm install dompurify @types/dompurify`. Export `sanitizeHtml(html: string): string` that strips `<script>`, `onclick`, `onerror` etc. while preserving `<table>`, `<img>`, structural HTML. | Sanitized HTML renders without scripts, tables preserved | 0.5h |
| 2.7 | Frontend: Document store integration | `store/useAppStore.ts`, `api/client.ts` | Add `documentHtml`, `documentTables`, `currentDocumentPdf` state. Add `loadDocumentHtml`, `loadDocumentTables` actions. Add `getDocumentHtml`, `getDocumentTables` API functions. | Store correctly fetches and caches document HTML and table metadata | 1h |
| 2.8 | Frontend: Loading and empty states | `components/DocumentTab.tsx` | Loading state: skeleton placeholder (gray rectangles). Empty state: "PDF를 업로드하세요" message with icon. Error state: error message with retry. | States display correctly in each scenario | 1h |
| 2.9 | Frontend: Wire document tab in App.tsx | `App.tsx` | Replace placeholder `case 'document'` with `<DocumentTab />`. | Clicking "문서 보기" tab shows the full document viewer | 0.5h |
| 2.10 | Performance: virtual scroll assessment | `components/DocumentViewer.tsx` | For large documents (100+ pages), evaluate if basic scroll is sufficient. If HTML > 500KB, implement lazy rendering: only render visible pages + buffer. Use IntersectionObserver. Decision: start with basic scroll (simpler). Only add virtualization if 100-page PDF renders > 2s. | 100-page PDF renders and scrolls smoothly (> 30fps) | 2.5h |

---

### Phase 3: Table Search Upgrade — 14h

> Prerequisites: Phase 1 complete (table types)

| # | Task | Files | Specific Changes | Success Criteria | Time |
|---|------|-------|-------------------|------------------|------|
| 3.1 | Frontend: Search header enhancements | `components/SearchResults.tsx` or new wrapper | Add "HOT" badge (`bg-[#dbeafe] text-[#2563eb] rounded-md`) + "총 N개 표 인덱싱 완료" text to search results header. Add search time display "검색 소요: X.X초". | Header shows HOT badge, table count, and search time | 1h |
| 3.2 | Frontend: Table tags on search results | `components/SearchResults.tsx`, `components/TableTag.tsx` | Render `TableTag` on each search result card based on `table_type` from backend. Backend already has tags in table metadata — include in search response. | Each result card shows appropriate tag (재무제표, 리스크, etc.) | 0.5h |
| 3.3 | Frontend: "Smart 선택" badge | `components/SearchResults.tsx` | When `smartResult` is present, show blue-green "Smart 선택" badge on the primary result. On vector_results, don't show it. | Smart search result has "Smart 선택" badge | 0.5h |
| 3.4 | Frontend: Relevance score display | `components/SearchResults.tsx` | Show `XX.X%` score on each result card (convert float to percentage). Style: large bold blue text for primary, gray for others. | Each card shows relevance percentage | 0.5h |
| 3.5 | Backend: table transpose endpoint | `web_server.py` | New `POST /api/table-transpose/{pdf_name}/{table_id}`. Read table HTML from session data. Parse with pandas (HTML → DataFrame → transpose → HTML). Handle colspan/rowspan gracefully (strip them before transpose). Return `{ html: "..." }`. | Curl returns transposed table HTML; merged cells handled | 2.5h |
| 3.6 | Backend: table calculate endpoint | `web_server.py` | New `POST /api/table-calculate` with `{ question, pdf_name, table_id }`. Read table HTML from session. Build prompt with table data + question. Stream LLM response via SSE (reuse ZaiLLMClient streaming pattern from existing `/api/qa`). Include calculation steps in response. | Asking "3년 평균 성장률?" returns streaming answer with calculation | 2h |
| 3.7 | Frontend: TrendBadge component | `components/TrendBadge.tsx` (NEW) | Two variants: green (`bg-[#f0fdf4] text-[#16a34a] border-[#bbf7d0]`) with up arrow, red (`bg-[#fef2f2] text-[#ef4444] border-[#fecaca]`) with down arrow. Props: `label, value, direction`. | Badge renders with correct color and arrow | 0.5h |
| 3.8 | Frontend: TrendBadge integration | `components/SearchResults.tsx` | After LLM smart search, extract trend data from LLM response metadata (or add a lightweight trend extraction step). Display TrendBadge row below table. Fallback: hide if no trend data. | Trend badges show on search results with growth/decline percentages | 2h |
| 3.9 | Frontend: RecommendedQuestions component | `components/RecommendedQuestions.tsx` (NEW) | Horizontally wrapped list of question chips. Props: `questions: string[], onSelect: (q: string) => void`. Style: `rounded-full border border-border text-text-secondary hover:border-primary hover:text-primary`. | Chips render, clicking fires question | 0.5h |
| 3.10 | Frontend: Inline QA in search results | `components/SearchResults.tsx` | Add "이 표에 질문하기" button on each card. On click, expand inline QA area below card: show RecommendedQuestions (context-aware per table), text input, and response area. Wire to `askTableQuestion` store action and `POST /api/table-calculate` or existing `/api/qa`. Show answers in ChatBubble style. | Clicking "이 표에 질문하기" expands QA area, typing question returns streaming answer | 3h |
| 3.11 | Frontend: Transpose in inline QA | `components/SearchResults.tsx` | Add "표의 가로축과 세로축을 변경해줘" as a recommended question. When detected, call `transposeTable` action → display transposed table. | Transpose recommended question triggers table transpose and shows result | 1.5h |

---

### Phase 4: Q&A Tab (Document RAG) — 20h

> Prerequisites: Phase 1 complete. Phase 3 inline QA is independent (table QA already exists).

| # | Task | Files | Specific Changes | Success Criteria | Time |
|---|------|-------|-------------------|------------------|------|
| 4.1 | Backend: document chunking pipeline | `web_server.py` (or new `rag.py`) | New function `_chunk_and_index_document(session)`. Reads all PDF HTML files in session. Strips HTML → text. Uses `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`. Embeds with `SentenceTransformerEmbeddings`. Stores in ChromaDB collection `"doc_chunks_{session_id}"`. Call after upload completes. Set `session["document_chunks_ready"] = True`. | After upload, document chunks are in ChromaDB; query returns results | 4h |
| 4.2 | Backend: ask-document endpoint | `web_server.py` | New `POST /api/ask-document` with `{ question }` + `X-Session-ID`. If `document_chunks_ready` is False, trigger chunking first. Embed question → search `"doc_chunks_{session_id}"` → top 5. Build system prompt: "AI 심사역 페르소나, 한국어, 금융 데이터 분석가". Stream LLM response via SSE with source metadata. Include page numbers from chunk metadata. Format: SSE events `{"token": "..."}`, `{"sources": [...]}`, `{"done": true}`. | Curl returns streaming answer with source citations | 4h |
| 4.3 | Frontend: QAPanel layout | `components/QAPanel.tsx` (NEW) | Three-section layout matching mockup: (1) Header bar: "AI 심사역" title + green dot "문서 이해 완료" badge + "대화 초기화" button. (2) Message list: scrollable area with messages. (3) Input bar: textarea + send button + disclaimer text. Full height `calc(100vh - 340px)`. | Layout matches mockup structure | 2h |
| 4.4 | Frontend: ChatBubble component | `components/ChatBubble.tsx` (NEW) | Two variants: AI bubble (gray bg, rounded left) and user bubble (blue bg, white text, rounded right). AI avatar: blue square with sparkles icon. User avatar: gray circle with "신" initial. AI bubble supports: rich text (bold, lists), inline tables, source chips. Loading state: spinning border + "문서를 검색하고 계산 중...". | Both bubble types render correctly; loading animation works | 2.5h |
| 4.5 | Frontend: SourceChip component | `components/SourceChip.tsx` (NEW) | Blue pill: `bg-[#dbeafe] text-[#1d4ed8] rounded-full`. Shows "p.N 표제목" with file-text icon. Clickable — scrolls to source in document tab (future enhancement; for now, just visual). | Source chips render with page number and title | 0.5h |
| 4.6 | Frontend: Recommended questions in QA | `components/QAPanel.tsx`, `components/RecommendedQuestions.tsx` | Show recommended questions at top of chat: "부채비율 추이?", "PF대출 만기?", "담보가치 변동 리스크?". Hardcoded initially. On click, trigger ask-document. After first question, hide or move to bottom. | Clicking recommended question triggers document QA | 0.5h |
| 4.7 | Frontend: QA store integration | `store/useAppStore.ts`, `api/client.ts` | Add `qaMessages`, `askDocument`, `clearQA`, `addQAMessage`, `updateQAMessage` to store. Add `askDocument` API function that handles SSE streaming, token accumulation, and source extraction. | Store correctly manages QA messages and streaming state | 2h |
| 4.8 | Frontend: AI greeting message | `components/QAPanel.tsx` | On mount (when document chunks ready), show AI greeting: "안녕하세요. {sessionName}의 문서를 모두 읽었습니다. 총 {totalPages}페이지, {totalTables}개의 표를 분석하였습니다." Styled as AI ChatBubble. | Greeting appears when QA tab is opened with documents loaded | 0.5h |
| 4.9 | Frontend: Wire QA tab in App.tsx | `App.tsx` | Replace placeholder `case 'qa'` with `<QAPanel />`. Pass session state (pages, tables count). | Clicking Q&A tab shows full chat interface | 0.5h |
| 4.10 | Frontend: Empty/loading/error states | `components/QAPanel.tsx` | Empty: "문서를 먼저 업로드하세요" with upload prompt. Loading: streaming shows tokens in real-time. Error: red error bubble. | All three states display correctly | 0.5h |
| 4.11 | Frontend: "대화 초기화" + disclaimer | `components/QAPanel.tsx` | Reset button clears `qaMessages` and re-shows greeting. Disclaimer: "AI 답변은 문서 기반이지만, 최종 결정은 심사역의 검토가 필요합니다." at bottom. | Reset clears chat; disclaimer always visible | 0.5h |

---

### Phase 5: Styling & Polish — 10h

> Prerequisites: Phases 1-4 complete

| # | Task | Files | Specific Changes | Success Criteria | Time |
|---|------|-------|-------------------|------------------|------|
| 5.1 | Pretendard font setup | `web/index.html` | Add Pretendard CDN link (already in mockup line 8-9). Verify it loads and applies via Tailwind `--font-sans` override. | Text renders in Pretendard font | 0.5h |
| 5.2 | Tailwind color tokens | `web/tailwind.config.js` or `tailwind.config.ts` | Add custom colors matching mockup: `sidebar: '#1e293b'`, `primary: '#2563eb'`, `primary-hover: '#1d4ed8'`, `surface: '#f8fafc'`, `border: '#e2e8f0'`, etc. Map to Tailwind theme. | All mockup colors available as Tailwind classes | 1h |
| 5.3 | CSS class porting | `web/src/index.css` | Port mockup custom CSS: `.tab-active`, `.tab-inactive`, `.card-elevated`, `.fade-in`, `.table-rendered`, `.chat-bubble-ai`, `.chat-bubble-user`, `.source-chip`, `.doc-page`, `.table-highlight`, `.session-active`, `.session-item`. Convert to Tailwind `@apply` or keep as utility classes. | All mockup styles render identically | 1.5h |
| 5.4 | Animation polish | Various components | Add `fade-in` animation on tab switches. Add transition effects on hover states. Add smooth scrolling for page jumps in PageSidebar. | Animations feel smooth and match mockup | 1h |
| 5.5 | Loading skeletons | Various components | Add skeleton loaders for: DocumentViewer (page-shaped rectangles), SearchResults (card-shaped rectangles), QAPanel (bubble-shaped rectangles). Use Tailwind `animate-pulse`. | Skeletons show during data loading | 1h |
| 5.6 | Empty states | Various components | Design empty states for: no documents uploaded, no search results, no QA messages yet. Each with icon + message + CTA. | Each empty state is informative and actionable | 1h |
| 5.7 | Responsive behavior | All layout components | Ensure: Global sidebar stays fixed (hidden on mobile with hamburger toggle — optional). Document viewer scroll works. Search results stack on narrow screens. Q&A panel full height. | App is usable at 1024px+ viewport width | 1.5h |
| 5.8 | Accessibility pass | All interactive elements | Add `aria-label` to buttons, `role` to lists, keyboard navigation for tabs, focus management. Ensure color contrast meets WCAG AA. | Keyboard-only navigation works for core flows | 1.5h |

---

## 7. Dependency Installations

```bash
# Frontend (web/)
cd web
npm install lucide-react dompurify @types/dompurify

# Backend (root) — pandas likely already a transitive dependency
pip install pandas  # only if not already installed
```

No other dependencies needed. LangChain, ChromaDB, opendataloadpdf, FastAPI, Zustand, Tailwind — all already present.

---

## 8. Data Flow Diagrams

### 8.1 PDF Upload (Enhanced)

```
User drops PDFs → Sidebar/SessionHeader upload handler
  → api.uploadPdfs(files, sessionId) → POST /api/upload
  → Backend: PDFProcessor.load_documents(use_hybrid=True)
    → opendataloader_pdf.convert(format="html, json")
    → Extract HTML tables + JSON metadata → LangChain Documents
    → _classify_table_type() for each table → store table_type
    → Save html_path, page_count, tables (with types) to session
    → _chunk_and_index_document(session) → ChromaDB doc_chunks collection
  → Response: { session_id, pdfs: { name: { table_count, page_count } }, total_tables }
  → Store: update pdfs, totalTables, totalPages
  → UI: SessionHeader PDF badges update, Sidebar session stats update
```

### 8.2 Document Viewer

```
User clicks "문서 보기" tab → store.setActiveTab('document')
  → DocumentTab renders
  → Auto-select first PDF → store.loadDocumentHtml(pdfName) + loadDocumentTables(pdfName)
  → API: GET /api/documents/{pdfName}/html → full HTML string
  → API: GET /api/documents/{pdfName}/tables → [{ table_id, title, page_number, table_type }]
  → DocumentViewer: sanitizeHtml(html) → parse → insert page dividers → render
  → PageSidebar: render document list, page links, table list with TableTag
  → User clicks page link → scroll to #page-N anchor
  → User hovers table → TableInDocument shows copy/Excel buttons
```

### 8.3 Table Search (Enhanced)

```
User types query → SearchBar → handleSearch(query, smart=true)
  → POST /api/smart-search (SSE)
  → Backend: vector search → LLM rerank → select best
  → Response: { result: { ..., table_type, relevance_score }, vector_results: [...] }
  → Store: setSearchResults
  → SearchResults renders cards:
    → TableTag (from table_type)
    → "Smart 선택" badge (if primary smart result)
    → Relevance score (XX.X%)
    → TrendBadge row (from trend analysis)
    → "이 표에 질문하기" button
  → User clicks "이 표에 질문하기" → expand inline QA
    → RecommendedQuestions chips appear
    → User asks "3년 평균 성장률?" → POST /api/table-calculate → stream answer
    → User asks "가로축 변경" → POST /api/table-transpose → show transposed table
```

### 8.4 Document Q&A

```
User clicks Q&A tab → QAPanel renders
  → Check document_chunks_ready → show "문서 이해 완료" green dot
  → Show AI greeting bubble
  → Show recommended questions chips
  → User types question → store.askDocument(question)
  → POST /api/ask-document (SSE)
  → Backend: embed question → search doc_chunks → top 5 chunks
    → Build prompt (AI 심사역 persona + chunks + question)
    → Stream tokens + sources
  → Store: addQAMessage({ role: 'ai', content: accumulated tokens, sources })
  → QAPanel: render ChatBubble with streaming text + SourceChips
```

---

## 9. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Large PDF HTML (>5MB) slow render | Document viewer unusable | Medium | Start with basic scroll; add IntersectionObserver lazy rendering if >500KB. Budget 2.5h in Phase 2.10. |
| Document chunking quality poor | Q&A answers inaccurate | Medium | Use RecursiveCharacterTextSplitter with Korean-friendly chunk size (1000 chars). Add metadata (page number, section title). |
| Table type classification inaccurate | Wrong tags shown | Low | Simple keyword heuristic is sufficient for finance documents. Allow "기타" fallback. |
| Transpose fails on complex tables | Feature broken | Medium | Strip colspan/rowspan before transpose. Catch errors gracefully, show original table. |
| ChromaDB collection name collision | Wrong chunks returned | Low | Use session-scoped collection name `"doc_chunks_{session_id}"`. |
| SSE connection drops during streaming | Partial answer shown | Low | Reconnect logic in API client. Show error state with retry button. |
| Session data loss on server restart | All data gone | High (by design) | In-memory is accepted for now. Document this limitation. Future: SQLite persistence. |

---

## 10. Verification Strategy

| Phase | Method | Criteria |
|-------|--------|----------|
| Phase 1 | Manual API testing + visual check | curl returns table types; Sidebar shows session history with stats |
| Phase 2 | Visual comparison with mockup | Document viewer renders full HTML; page dividers visible; table hover works |
| Phase 3 | Functional testing | Search shows tags, score, badges; inline QA works; transpose works |
| Phase 4 | End-to-end testing | Upload → Q&A: ask question → get streaming answer with sources |
| Phase 5 | Visual pixel comparison | Side-by-side mockup vs live app; responsive at 1024px+ |
| All phases | `npm run build` | Exit code 0, no TypeScript errors |
| All phases | `lsp_diagnostics` | All .tsx/.ts files clean (0 errors) |

---

## 11. Time Summary

| Phase | Description | Time |
|-------|-------------|------|
| Phase 0 | Pre-flight (COMPLETE) | 0h |
| Phase 1 | Foundation Upgrades | 8h |
| Phase 2 | Document Viewer | 16h |
| Phase 3 | Table Search Upgrade | 14h |
| Phase 4 | Q&A Tab (Document RAG) | 20h |
| Phase 5 | Styling & Polish | 10h |
| **Total** | | **68h** |

> **Note on estimation**: These are implementation-ready estimates assuming a senior developer with full context. Phase 4 (RAG) and Phase 2 (DocumentViewer) carry the most technical risk. Buffer 20% for unknowns → **~82h realistic total**.

---

## 12. Execution Order

```
Phase 0 (DONE)
    ↓
Phase 1 (Foundation: table types, session history, icons)
    ↓
Phase 2 (Document Viewer: depends on table types from Phase 1)
    ↓ ↑ (Phase 3 and Phase 4 can be parallelized)
Phase 3 (Search Upgrade: depends on table types from Phase 1)
Phase 4 (Q&A RAG: depends on chunking pipeline)
    ↓
Phase 5 (Polish: depends on all features being complete)
```

Phase 3 and Phase 4 are independent and can be worked on in parallel after Phase 1+2 complete.

---

## 13. File Creation/Modification Summary

### New Files (16)

```
web/src/components/DocumentTab.tsx
web/src/components/PageSidebar.tsx
web/src/components/DocumentViewer.tsx
web/src/components/TableInDocument.tsx
web/src/components/QAPanel.tsx
web/src/components/ChatBubble.tsx
web/src/components/TrendBadge.tsx
web/src/components/TableTag.tsx
web/src/components/RecommendedQuestions.tsx
web/src/components/SourceChip.tsx
web/src/utils/sanitizeHtml.ts
web/src/types/document.ts          # TableMeta, QAMessage, SessionSummary types
```

### Modified Files (10)

```
web/src/App.tsx                     # Wire DocumentTab and QAPanel
web/src/store/useAppStore.ts        # Add new state fields and actions
web/src/api/client.ts               # Add new API functions
web/src/components/Sidebar.tsx      # Session history, stats, version footer
web/src/components/SessionHeader.tsx # Per-PDF badges, "PDF 추가" button
web/src/components/SearchResults.tsx # Tags, badges, score, inline QA, trend
web/src/components/SearchBar.tsx    # Minor style tweaks
web/src/index.css                   # Port mockup CSS classes
web/tailwind.config.ts              # Color tokens
pdftablesearch/web_server.py        # New endpoints + table types + chunking
```

---

## 14. Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2025-05-12 | v1.0 | Initial draft |
| 2025-05-12 | v2.0 | Momus feedback: tech decisions locked, time estimates doubled |
| 2025-05-12 | v3.0 | **Final version**: Full code audit, Phase 0 resolved, dual sidebar clarified, all mockup features cataloged, existing code accounted for, realistic estimates with risk buffer |

---

## Next Step

This plan is **implementation-ready**. Begin with **Phase 1, Task 1.1** (backend table type classification). Each task has explicit file paths, specific changes, and success criteria. No ambiguous decisions remain.
