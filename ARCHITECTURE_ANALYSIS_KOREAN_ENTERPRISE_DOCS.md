# Korean Enterprise Document Analysis: Strategic Architecture Blueprint

## 1. Executive Summary

This analysis evaluates the leading tools, architectures, and market players for building a **Korean enterprise document analysis MVP** with four core capabilities:
1. **Table Semantic Search** (existing)
2. **IM / Corporate Report Analysis** (positive/negative acquisition factors)
3. **One-Page Executive Summary Generation**
4. **Document-Grounded Q&A (RAG)**

The recommended architecture centers on **Upstage Document Parse** for Korean document ingestion, a **hierarchical tree-index RAG** (PageIndex/TreeRAG pattern) for document-level understanding, and **Vercel AI SDK + LangChain** for the application layer.

---

## 2. Document Understanding: PDF, Text, Tables & Figures

### 2.1 Comparison of Leading Document Parsing Tools

| Tool | Type | Korean Support | HWP Support | Mixed KOR-ENG | Key Strengths | Best For |
|------|------|----------------|-------------|---------------|---------------|----------|
| **Upstage Document Parse** | Cloud API | **Native / Best-in-class** | PDF output only | **Excellent** | 95%+ OCR accuracy, layout analysis, table/chart extraction, 1,000 pages/file, agentic workflows | **Primary choice for Korean enterprise docs** |
| **Docling** | Open-source (MIT) | Via OCR (language-agnostic TableFormer) | ❌ No native | Good | Local execution, advanced layout (Heron), table structure, LangChain/LlamaIndex integration, MCP server | Local/offline processing, non-Korean docs, air-gapped environments |
| **LlamaParse** | Cloud API | **Yes (80+ languages)** | ❌ No | Good | Agentic parsing tiers, financial document optimized, schema-driven extraction, cost optimizer for mixed docs | Financial RAG, 10-Ks, English-heavy investment docs |
| **Google Document AI** | Cloud API | **Yes (KO supported)** | ❌ No | Good | Gemini Layout Parser, context-aware chunking, 200+ language OCR, specialized financial parsers (invoice, bank statement) | GCP-native stacks, structured form extraction |
| **Azure Document Intelligence** | Cloud API | Yes | ❌ No | Good | Custom model training, prebuilt financial models, strong table extraction | Microsoft-centric enterprises |
| **Unstructured** | Open-source | General | ❌ No | Good | Fast partitioning, diverse file types, local-first | General-purpose chunking, English docs |

### 2.2 Korean-Specific Format Handling (HWP/HWPX)

Korean enterprises (government, legal, finance) still widely use **HWP/HWPX** (Hancom Office). None of the major document AI platforms parse HWP natively.

**Recommended Pre-Processing Pipeline:**
1. **Convert HWP → PDF** before parsing:
   - `simple-hwp2pdf` (PyPI): Dual-engine (standalone for HWPX, Office engine for HWP). No JVM needed for HWPX.
   - `rhwp-python` (Rust-based, MIT license): 62× faster than `pyhwp`, supports HWP+HWPX via same API, includes `HwpLoader` for LangChain integration.
   - `hwp-hwpx-parser` (pure Python, Apache 2.0): Extracts text, tables (markdown/CSV), footnotes, images, hyperlinks. JVM not required.
2. **Parse PDF** through Upstage Document Parse or Docling.
3. **Alternative:** `hwpx-toolkit` provides end-to-end extraction + vectorization + RAG pipeline specifically for Korean government/enterprise documents.

**Verdict for Korean MVP:**
- **Primary:** Upstage Document Parse (best Korean OCR accuracy, table/chart/layout understanding, tested by Samsung Life Insurance, KB Kookmin Bank).
- **Fallback/Local:** Docling (if data cannot leave premises).
- **HWP bridge:** `simple-hwp2pdf` + `rhwp-python`.

---

## 3. Document-Level RAG Architectures

Traditional chunk-and-embed RAG destroys document structure, loses cross-references, and splits tables mid-row. Modern approaches treat the document as a **structured artifact** rather than a flat bag of chunks.

### 3.1 Architectural Patterns

#### A. Hierarchical Tree Index (PageIndex / TreeRAG)
- **Concept:** Build a navigable tree from the document’s actual structure (Table of Contents → Sections → Pages). LLM agent traverses the tree to locate relevant branches.
- **Pros:** No vector DB needed, 100% traceability, preserves cross-references, 90%+ context reduction via deep traversal.
- **Cons:** Requires good document parsing upfront, LLM latency for tree traversal.
- **Implementation:** `PageIndex` (open-source) or `TreeRAG` (production-ready, Korean/English/Japanese supported).
- **Use Case:** Ideal for long regulatory/financial reports where section hierarchy matters.

#### B. Agentic Multi-Modal RAG (DocAgent / MDocAgent)
- **Concept:** Multiple specialized agents (general agent, text agent, image agent, reviewer agent) collaborate. Outline construction → tool-based retrieval → answer synthesis.
- **Pros:** Handles multi-modal evidence (text + charts + tables), cross-page reasoning, human-like reading behavior.
- **Cons:** Higher complexity, multiple LLM calls.
- **Implementation:** LangChain/LangGraph with tool-calling, or frameworks like `DocAgent` (EMNLP 2025).

#### C. Vision-First Retrieval (ColPali / VisionRAG)
- **Concept:** Embed document **page images** directly using Vision-Language Models (VLMs), skipping OCR entirely. Query tokens interact with image patch embeddings via late interaction (ColBERT-style MaxSim).
- **Pros:** No layout parsing heuristics, captures fonts, colors, spatial relationships, table structure implicitly. Outperforms text-only RAG on visually complex financial docs.
- **Cons:** Storage-heavy (but token pooling reduces by ~66%), needs GPU for indexing.
- **Models:** `ColPali` (PaliGemma-3B), `ColQwen2`, `VisionRAG` (pyramid indexing: page/section/fact/hotspot levels).
- **Best For:** Documents where visual layout encodes meaning (financial reports with complex tables, investor decks).

#### D. Hierarchical Multi-Modal Chunking (MultiDocFusion / MHier-RAG)
- **Concept:** Combine visual layout detection → OCR → LLM-based section hierarchy parsing (DSHP-LLM) → DFS-based chunk assembly. Creates in-page chunks + topological cross-page chunks.
- **Pros:** Explicitly preserves section hierarchy and multi-modal dependencies. 8–15% retrieval precision improvement.
- **Implementation:** Custom pipeline using layout detection + Docling/Upstage for structure + DFS chunking.

#### E. Vectorless Agentic RAG (NanoIndex)
- **Concept:** Build entity graphs + document trees + pixel citations. Agent navigates trees and follows graph edges for cross-references.
- **Pros:** Cited answers down to bounding boxes, no embedding model tuning.
- **Cons:** Newer, less ecosystem maturity.

### 3.2 Recommended RAG Architecture for the MVP

**Hybrid Hierarchical + Vision-First RAG**

```
Document Input (PDF / HWP→PDF)
        ↓
[ Upstage Document Parse ]  →  Structured Markdown + Table JSON + Page Images
        ↓
                    ┌─────────────────────────────┐
                    ↓                             ↓
        [ Text RAG Pipeline ]          [ Vision RAG Pipeline ]
        - Hierarchical tree index        - ColPali page embeddings
        - Section-aware chunks           - Late interaction retrieval
        - Table rows as nodes            - Visual context retrieval
                    ↓                             ↓
                    └─────────────────────────────┘
                                ↓
                    [ Reciprocal Rank Fusion ]
                                ↓
                    [ LLM Agent Synthesis ]
                        (Claude/GPT-4o/Solar)
```

**Why this hybrid?**
- Korean financial reports contain **dense tables** that Upstage parses well into structured text, but also **charts/layouts** where visual context matters.
- Text RAG provides exact numerical retrieval and cross-reference verification.
- Vision RAG ensures nothing is lost when layout carries semantic meaning.
- RRF (Reciprocal Rank Fusion) combines both signals.

---

## 4. Fintech AI Features for IM & Corporate Analysis

### 4.1 Market Landscape

Leading products in AI-powered investment/corporate analysis:

| Product | Core Features | Red Flags | Memo Gen | Due Diligence | Cross-Reference |
|---------|--------------|-----------|----------|---------------|-----------------|
| **Dili** | Custom workflows, IC memo generation, risk flags, intelligent search | ✅ | ✅ | Deep | ✅ |
| **SowFin** | 150+ risk factor scoring, synergy ID, deal memo, competitive intel | ✅ | ✅ | Deep | ✅ |
| **Photon Insights** | Automated QoE reports, investment memo, trend analysis | ✅ | ✅ | Medium | ✅ |
| **CorpDev.Ai** | Executive summary, market analysis, financial assessment, synergy modeling | ⚠️ | ✅ | Medium | ✅ |
| **PinpointAI** | QoE reports, red flag detection, financial charts | ✅ | ✅ | Deep | ✅ |
| **Lumenai** | Screening agent, memo creation, buyer Q&A, portfolio monitoring | ✅ | ✅ | Deep | ✅ |
| **SYNSA** | 20+ specialist agents, financial metrics, market benchmarking | ✅ | ✅ | Deep | ✅ (3+ agent consensus) |
| **ZenCheck** | Conflict detection, consistent messaging, diligence reports | ✅ | ⚠️ | Medium | ✅ |

### 4.2 Specific AI Capabilities for IM Analysis

Based on the competitive landscape, the following features are table-stakes for a modern IM/corporate analysis product:

1. **Automated Due Diligence**
   - Extract and structure financial metrics (Revenue, EBITDA, margins, cash flow) from statements.
   - Cross-verify figures across multiple document sources (audited statements vs. management accounts).
   - Detect YoY trend anomalies.

2. **Red Flag Detection**
   - Identify deal-breakers: change-of-control clauses, contingent liabilities, revenue concentration, related-party transactions.
   - Flag inconsistencies between narrative and numbers.
   - Detect missing disclosures vs. regulatory checklists.

3. **SWOT / Factor Analysis**
   - Generate Strengths, Weaknesses, Opportunities, Threats from narrative sections.
   - Distinguish **positive acquisition factors** (market position, technology moat, margin expansion) vs.
     **negative factors** (customer churn, legal risks, margin compression).

4. **Executive Summary Generation**
   - One-page synthesis: Investment thesis, KPI snapshot, risks & open questions, next steps.
   - Must be **grounded** with citations to specific document pages/sections.

5. **Cross-Reference Verification**
   - Ensure narrative claims match table data (e.g., “revenue grew 30%” aligns with income statement).
   - Detect contradictions across sections.

6. **Document-Grounded Q&A**
   - Answer specific questions with citations (page-level or bounding-box level).
   - Handle multi-hop reasoning ("What was the EBITDA margin in FY2019?" → find income statement → compute).

### 4.3 Prompt Engineering Framework for IM Analysis

The most effective pattern seen in production tools (Dili, SowFin, V7 Go) is:
- **Domain-specific instruction templates** tuned for each deal type (PE buyout, VC growth, distressed M&A).
- **Multi-agent validation:** At least 2-3 agent perspectives before surfacing a finding (SYNSA’s consensus validation).
- **Glass-box AI:** Every claim must cite the exact source location.

---

## 5. Korean & Global Startup/Product Ecosystem

### 5.1 Upstage (Korea) — Critical Partner
- **Status:** Korea’s first AI unicorn ($130M Series C, $720M+ valuation).
- **Products:**
  - **Document Parse:** Layout-aware OCR with 95%+ accuracy on Korean docs. Supports tables, charts, equations, 1,000 pages/file.
  - **Information Extract:** Zero-shot structured data extraction from any document.
  - **Solar LLM / Solar Pro:** Enterprise-grade LLM optimized for Korean, English, Japanese. Strong finance/legal domain performance.
  - **Upstage Studio:** No-code agentic platform for document processing workflows.
- **Integrations:** Native `langchain-upstage` package (`UpstageDocumentParseLoader`), AWS Marketplace, on-prem deployment.
- **Why it matters:** If you are building a Korean financial document product, Upstage is the **single best parsing layer** available. Their LangChain loader outputs HTML/text/markdown with coordinates.

### 5.2 Nota AI (Korea)
- Focus: On-device AI optimization, model quantization, edge deployment.
- Relevance: **Low direct relevance** to document understanding; primarily model compression/infrastructure. Could be useful later for on-prem LLM deployment.

### 5.3 Global Players in Fintech Document AI
- **Dili, SowFin, Lumenai, SYNSA** — All prove there is strong product-market fit for AI diligence platforms.
- Differentiators: Multi-agent consensus, firm-specific workflow customization, pixel-level citations.

### 5.4 Vercel AI SDK & LangChain Patterns
- **Vercel AI SDK:** Best-in-class TypeScript toolkit for streaming, structured output (`generateObject`), tool calling, and multi-provider LLM support (OpenAI, Anthropic, Google, Upstage).
- **LangChain:** Mature Python/JS ecosystem. Use `UpstageDocumentParseLoader` directly. LangGraph enables cyclic agent workflows for multi-step due diligence.
- **Recommended stack:** Next.js + Vercel AI SDK (frontend/agent orchestration) + Python FastAPI backend (document parsing, embedding, vector DB).

---

## 6. Recommended MVP Architecture

### 6.1 System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT (Next.js)                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                    │
│  │ Tab 1    │  │ Tab 2    │  │ Tab 3    │  │ Tab 4    │                    │
│  │ Tables   │  │ IM       │  │ Executive│  │ Doc Q&A  │                    │
│  │ Search   │  │ Analysis │  │ Summary  │  │ (RAG)    │                    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                      ┌───────────────┴───────────────┐
                      ↓                               ↓
┌─────────────────────────────┐         ┌─────────────────────────────┐
│   Vercel AI SDK (TS)        │         │   Python API (FastAPI)      │
│  - Streaming UI             │         │  - Document Ingestion       │
│  - Tool Calling             │         │  - Hierarchical Indexing    │
│  - Structured Output        │         │  - Vector Store             │
│  - Multi-provider LLM       │         │  - Vision Embedding         │
└─────────────────────────────┘         └─────────────────────────────┘
```

### 6.2 Layer-by-Layer Recommendations

#### Layer 1: Document Ingestion & Parsing
| Component | Recommendation | Rationale |
|-----------|---------------|-----------|
| **Primary Parser** | **Upstage Document Parse API** | Best Korean OCR + layout + table accuracy. Native LangChain integration. Outputs HTML/Markdown with coordinates. |
| **HWP Pre-processor** | `simple-hwp2pdf` or `rhwp-python` | Handles HWP/HWPX → PDF conversion before parsing. |
| **Fallback/Local** | **Docling** | MIT license, local execution, advanced layout model (Heron), good table structure. Use if data residency prevents cloud APIs. |
| **Scanned Image OCR** | Upstage (force mode) or Google Document AI | Upstage handles skewed/rotated scans better for Korean. |

#### Layer 2: Document Representation & Storage
| Component | Recommendation | Rationale |
|-----------|---------------|-----------|
| **Structured Export** | Markdown + JSON (tables) + Page Images | Preserve hierarchy, tables as structured data, images for vision RAG. |
| **Hierarchical Index** | **PageIndex / TreeRAG format** | Document tree with section summaries, page ranges, cross-references. |
| **Text Embeddings** | `text-embedding-3-large` (OpenAI) or `UpstageEmbeddings` | Consider Upstage embeddings for Korean semantic alignment. |
| **Vision Embeddings** | **ColPali (PaliGemma-3B) or ColQwen2** | Embed page images for visual retrieval. Open-source, integrates with Qdrant/Milvus/Weaviate. |
| **Vector DB** | **Qdrant** or **Pinecone** | Qdrant supports multi-vector (ColPali) natively; Pinecone has broader LangChain support. |
| **Relational / Graph** | Neo4j or in-memory graph | For entity extraction and cross-reference verification (Company → Metric → Document Section). |

#### Layer 3: Retrieval & Reasoning
| Component | Recommendation | Rationale |
|-----------|---------------|-----------|
| **Retrieval Strategy** | **Hybrid: Hierarchical Text + Vision** | Text RAG for exact numbers and citations; Vision RAG for layout-heavy pages. Fuse with RRF. |
| **Agent Framework** | **LangGraph (Python)** or **Vercel AI SDK tools** | LangGraph for complex multi-step due diligence workflows; Vercel AI SDK for simpler Q&A. |
| **Cross-Reference Tool** | Custom tool: graph query over extracted entities | Verify narrative claims against table data using structured extraction. |
| **Citation** | Page-level + bounding box (if using Upstage coordinates) | Essential for trust in financial analysis. |

#### Layer 4: Analysis & Generation (Per Tab)

**Tab 1: Table Semantic Search (Existing)**
- **Action:** Keep current approach; ensure tables are parsed by Upstage/Docling into structured formats (CSV/JSON).
- **Enhancement:** Embed table rows with surrounding context (section header + paragraph before/after) for semantic search that understands what the table means, not just raw cell values.

**Tab 2: IM / Corporate Report Analysis**
- **Pipeline:**
  1. Parse document → Extract sections (Business Overview, Financials, Risks, Legal).
  2. **Multi-pass LLM analysis:**
     - Pass 1: Extract structured financial metrics.
     - Pass 2: Generate SWOT from narrative sections.
     - Pass 3: Identify red flags (agent runs checklist against extracted data).
     - Pass 4: Score positive/negative acquisition factors with evidence citations.
  3. **Consensus validation:** Run 2-3 parallel LLM agents with different reasoning paths; surface only agreed findings (like SYNSA).
- **Output:** Structured JSON → Rendered as interactive cards (Positive Factors | Negative Factors | Red Flags).

**Tab 3: One-Page Executive Summary**
- **Pipeline:**
  1. Feed full document hierarchy (tree index with section summaries) to LLM.
  2. Use structured generation (`generateObject` in Vercel AI SDK) with schema:
     - Investment Thesis (3-5 bullets)
     - KPI Snapshot (6-10 metrics with values)
     - Key Risks (2-4 items)
     - Recommended Next Steps (3-6 actions)
  3. **Grounding:** Require every bullet to cite source page numbers.
- **Model:** Claude 3.5/3.7 Sonnet (strong long-context) or GPT-4o. If Korean fluency is critical, route to Upstage Solar Pro.

**Tab 4: Document-Grounded Q&A (RAG)**
- **Pipeline:**
  1. User asks question.
  2. Router agent classifies intent (factual lookup, trend analysis, comparison, calculation).
  3. Retrieve from **both** text index (hierarchical chunks) and vision index (ColPali page images).
  4. Re-rank with RRF.
  5. Synthesis LLM answers with citations.
  6. **Cross-reference check:** If answer involves a number, verify against extracted table data.
- **Advanced:** For calculation questions ("What was the EBITDA margin in FY2019?"), use a tool that queries structured table data, not just narrative chunks.

### 6.3 Technology Stack Summary

| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 14+ (App Router), Tailwind, shadcn/ui |
| **AI SDK** | Vercel AI SDK (TypeScript) — streaming, structured objects, tool calling |
| **Backend** | FastAPI (Python) for document processing + LangGraph agents |
| **Document Parsing** | **Upstage Document Parse** (primary) + **Docling** (fallback) |
| **HWP Conversion** | `simple-hwp2pdf` / `rhwp-python` |
| **Text Embeddings** | OpenAI `text-embedding-3-large` or `UpstageEmbeddings` |
| **Vision Retrieval** | **ColPali** (Hugging Face `vidore/colpali-v1.2`) |
| **Vector DB** | **Qdrant** (multi-vector support) or Pinecone |
| **Graph DB** | Neo4j (optional, for cross-reference verification) |
| **LLM** | Claude 3.5/3.7 Sonnet or GPT-4o (primary); Upstage Solar Pro (Korean-heavy docs) |
| **Agent Framework** | LangGraph (Python) for complex reasoning; Vercel AI SDK tools for simpler flows |
| **Storage** | PostgreSQL (metadata) + S3/Cloudflare R2 (page images, raw docs) |
| **Deployment** | Vercel (frontend) + AWS/GCP (backend, GPU for ColPali indexing) |

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-3)
1. Set up **Upstage Document Parse** integration via `langchain-upstage`.
2. Build HWP → PDF conversion pipeline (`simple-hwp2pdf`).
3. Implement **hierarchical document tree** extraction from parsed output.
4. Store structured tables in PostgreSQL; store page images in S3.

### Phase 2: Core RAG (Weeks 4-6)
1. Build **text-based hierarchical RAG** with section-aware chunks.
2. Integrate **ColPali** for vision-first retrieval on page images.
3. Implement **RRF fusion** between text and vision retrievers.
4. Build Tab 4 (Document Q&A) with citation support.

### Phase 3: Analysis Features (Weeks 7-9)
1. Build financial metric extraction pipeline from tables.
2. Implement **multi-agent due diligence** workflow (red flags, SWOT, factor scoring).
3. Build Tab 2 (IM Analysis) with positive/negative factor cards.
4. Build **executive summary generator** (Tab 3) with structured output schema.

### Phase 4: Polish & Scale (Weeks 10-12)
1. Add **cross-reference verification** tool (narrative vs. table data consistency).
2. Optimize embedding/indexing pipeline for 1,000+ page documents.
3. Add user feedback loop to improve retrieval relevance.
4. Performance benchmarking against FinanceBench-style tasks.

---

## 8. Key Differentiators for the Korean Market

1. **Upstage-native integration** gives best-in-class Korean OCR and layout understanding — a moat that generic document AI products cannot match.
2. **Hierarchical tree index** overcomes the “chunk boundary” problem common in English-centric RAG tutorials.
3. **Vision-first retrieval (ColPali)** handles Korean financial reports where table structure and visual cues encode critical information.
4. **Multi-agent consensus** for red-flag detection reduces hallucination risk — critical for high-stakes M&A decisions.
5. **HWP support** opens access to the vast corpus of Korean government and enterprise documents inaccessible to most global players.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Upstage API latency on 1,000-page docs | Async batch processing; pre-index on upload; use Docling for initial draft. |
| ColPali storage costs | Token pooling (pool factor 3 reduces vectors by 66% with 97.8% performance retained). |
| Korean-English mixed text quality | Use Upstage Solar Pro for generation; validate with Upstage Groundedness Check. |
| Hallucination in IM analysis | Multi-agent consensus + mandatory citation + structured output schemas (Zod/Pydantic). |
| HWP conversion errors | Dual-engine approach (standalone + office fallback); validate output page count. |

---

*End of Analysis*
