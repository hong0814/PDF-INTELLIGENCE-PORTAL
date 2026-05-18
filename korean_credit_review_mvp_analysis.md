# PDFTableSearch → Korean Corporate Finance Credit Review MVP

## Structured Market Analysis & Actionable Insights

---

## 1. DOCUMENT TYPES & TABLES IN KOREAN CORPORATE CREDIT REVIEW (기업금융심사)

### 1.1 Primary Document Categories

**A. Application Documents (신청서류)**
- 대출신청서 / 여신신청서 (Loan/Credit Application)
- 기업정보조회서 (Corporate Information Inquiry)
- 대표자인감서 (Representative Signature/Seal)

**B. Financial Statements (재무제표류)**
- 대차대조표 (Balance Sheet)
- 손익계산서 (Income Statement)
- 현금흐름표 (Cash Flow Statement)
- 부채현황표 (Debt Schedule)

**C. Collateral & Security (담보·보증서류)**
- 담보평가보고서 (Collateral Evaluation Report)
- 부동산평가서 (Real Estate Appraisal)
- 담보물건목록 (Collateral Item List)
- 권리증서 (Property Rights Documents)
- 보증서류 (Guarantee Documents)

**D. Business Planning (사업계획서류)**
- 사업계획서 (Business Plan)
- 수익성분석서 (Profitability Analysis)
- 시장분석서 (Market Analysis)
- 자금계획서 (Fund Usage Plan)

**E. NPL & Risk Reports (리스크관리서류)**
- 부실채권보고서 (NPL Reports)
- 신용평가보고서 (Credit Assessment Reports)
- 여신심사보고서 (Credit Review Reports)

**F. PF Loan Documents (PF대출 서류)**
- 사업타당성서 (Project Viability Document)
- 수주확약서 (Purchase Order Confirmation)
- 금융조합계획서 (Financial Syndication Plan)

### 1.2 Core Data Structures Extracted from PDFs

| Table Type | Key Korean Fields | Key Metrics |
|-----------|-------------------|-------------|
| **대차대조표 (Balance Sheet)** | 유동자산, 비유동자산, 유동부채, 비유동부채, 자본금, 이익잉여금 | Total Assets, Debt-to-Equity, Net Worth |
| **손익계산서 (Income Statement)** | 매출액, 영업이익, 영업외수익, 법인세비, 당기순이익 | Revenue, EBITDA, Net Margin, ROE, EPS |
| **현금흐름표 (Cash Flow)** | 영업활동현금흐름, 투자활동현금흐름, 재무활동현금흐름, 기초/기말 잔액 | Operating CF, Free CF, CF Adequacy |
| **재무비율표 (Ratio Table)** | 유동비율, 부채비율, 자기자본순이익률, 이자보상비율, 총자산회전률, 매출액영업이익률 | D/E, Current Ratio, Interest Coverage, ROE, ROA |
| **담보평가표 (Collateral)** | 담보물건명, 평가금액, 담보인정비율, 부채잔액, 담보가치 | LTV, Recovery Rate, Collateral Coverage |
| **현금흐름예측표 (CF Forecast)** | 연간현금유입, 현금유출, 순현금흐름, DSCR 계산 | DSCR, LLCR, Project IRR |

### 1.3 Complexity Factors in Korean PDFs
- Documents come in **HWP, PDF, scanned image** formats (often mixed)
- Language is **Korean + English** (e.g., K-IFRS vs Korean GAAP)
- Different formats per bank (KB, 신한, 하나, 우리 each have slightly different templates)
- **Multi-year statements** (3-5 years) require cross-period reconciliation
- PF loan documents are especially complex: multiple project entities, waterfall cash flows, completion guarantees

---

## 2. PAIN POINTS IN MANUAL CREDIT REVIEW & AI SOLUTIONS

### 2.1 Top Pain Points in Korean Bank Credit Review

| Pain Point | Manual Process Impact | AI/Automation Solution |
|-----------|----------------------|----------------------|
| **Multi-document data extraction** | Analysts manually enter data from 10+ document types; 2-4 hours per case | OCR + table extraction from PDFs → structured data in <5 min |
| **Cross-document verification** | Checking consistency between 대출신청서, 재무제표, 담보평가보고서 is error-prone | Automated cross-document reconciliation with discrepancy flags |
| **Ratio calculation & benchmarking** | 20-30 ratios calculated manually; takes 1-2 hours; high error risk | Automated ratio computation from extracted structured data; instant |
| **Trend analysis across periods** | Manual comparison of 3-5 years of financial data; tedious | Automated YoY trending with visual charts; anomaly detection |
| **Memo drafting (여신심사보고서)** | 4-8 hours to draft a comprehensive credit review memo | AI-generated draft memos with source citations; analyst as editor |
| **Collateral evaluation review** | Manual comparison of appraisal reports with loan terms | Automated LTV computation, recovery rate analysis, risk flags |
| **NPL monitoring & risk flags** | Periodic manual review of watch-list borrowers | Real-time flagging based on covenant breach, financial deterioration |
| **Regulatory documentation** | Ensuring compliance with FSC/FSS documentation standards | Automated checklists against regulatory requirements |
| **Work-cycle time** | Complex cases take 2-3 weeks from application to decision | Reduce to days by automating data-heavy preprocessing steps |
| **Expert dependency** | Senior analysts needed for complex cases; hard to scale | AI handles 80% of routine analysis; senior reviewers focus on judgment calls |

### 2.2 Quantified Impact Potential
- **Credit memo generation:** 4-8 hours → 30 minutes (90%+ time savings)
- **Data extraction from PDFs:** Manual entry reduced by 90% with 99%+ accuracy
- **Document review overhead:** 40% of underwriter time freed for value-added analysis
- **Loan processing speed:** 50% faster end-to-end with automated preprocessing
- **Labor cost savings:** Up to 30% reduction in analyst FTE for routine cases

---

## 3. EXISTING FINTECH/REGTECH TOOLS

### 3.1 Global Market Leaders

| Tool | Company | Key Capabilities | Credit Relevance |
|------|---------|-----------------|------------------|
| **Moody's Analytics** | Moody's | Financial data extraction, credit scoring, ECL modeling, risk benchmarks | Full credit lifecycle, but enterprise-grade & costly |
| **S&P Global Ratings** | S&P | Credit assessment, financial statement analysis, industry benchmarks | Gold standard for ratings; tools like CapIQ are market standard |
| **nCino** | nCino | LOS with AI underwriting, document management, workflow automation | 75% data re-keying reduction, 91% faster underwriting |
| **Aloan / Lendisys** | Commercial AI platforms | Automated data extraction, ratio calc, memo generation, source citations | Direct competitor space—80% memo completion before analyst writes |
| **CredStack / Inscribe** | Fraud/AML | Document forensics, tampering detection, anomaly detection in transactions | Fraud detection, risk flagging, AI-generated doc detection |
| **Stratyfy** | Decision intelligence | AI-driven credit decisioning, bias mitigation, risk modeling | Automated decision support with explainable AI |
| **ACTICO / Arya.ai** | AI credit platforms | LLM-based extraction, risk summarization, natural language queries | Emerging AI-native approach; NLQ for underwriters |
| **Ocrolus** | Document AI | PDF parsing, bank statement analysis, cash flow verification | Strong on unstructured doc parsing; used by US fintech lenders |
| **Ocrolus / Taktile** | Workflow/decision | Document AI + decision engine integration | Orchestration layer for AI-extracted data into decisions |

### 3.2 Korean-Specific Fintech/Regtech Tools

| Tool | Company | Key Capabilities | Relevance to Credit Review |
|------|---------|-----------------|---------------------------|
| **AI Credit Review Agent** | **Shinhan Bank** (internal) | GenAI-powered corporate data analysis; industry-specific models (12 sectors); collateral recovery valuation; standardized credit evaluation reports | **Direct benchmark**—Shinhan deployed this in March 2026 for internal corporate lending; proves banks are actively investing in this space |
| **RM Marketing Plus** | **NH NongHyup** | AI analyzes 467 variables for corporate lending; loan application probability scoring; RM sales support | Operational AI for corporate finance; signals market readiness |
| **ABACUS** | **AIZEN** | AutoML credit scoring, explainable AI (XAI), real-time credit cycle monitoring, MDM (master data management for borrowers), fraud detection (15K txns/min) | AI-native Korean fintech; strong on credit lifecycle; designated by Ministry of Science/ICT |
| **Antock (앤톡)** | Antock | Corporate big data platform; alternative credit rating for SMEs (non-financial data); tech scanner; growth prediction; IPO potential assessment | SME-focused alternative data; different niche but relevant for SMB lending |
| **finex** | finex | Agentic AI for FP&A; ERP ledger data analysis; rule-based algorithms for financial accuracy; automated reporting | Internal FP&A tool, not credit review, but similar tech stack (ERP → AI analysis) |
| **Fintag (핀태그)** | Fintag | AI financial asset management; real-time transaction analysis; anomaly detection; conversational AI via messenger | AI + Vector DB architecture; anomaly detection; relevant tech stack |

### 3.3 Market Gap Identified
**No Korean vendor is offering a standalone, bank-agnostic "table extraction + semantic search + automated credit analysis" product for PDF-based corporate credit review.**

- Major banks (Shinhan, NH) are building **internal** solutions
- Fintechs (AIZEN, Antock) focus on **scoring and alternative data**, not document analysis
- Global tools (Moody's, nCino) are **enterprise-priced** and not optimized for Korean document formats (HWP, K-GAAP templates)
- **Opportunity:** A purpose-built tool for Korean corporate finance credit reviewers that handles the specific document types, table formats, and regulatory context of the Korean market

---

## 4. ADDITIONAL CAPABILITIES NEEDED FOR CREDIT REVIEW MVP

### 4.1 Tier 1: MVP Critical (0-6 months)

These are the must-have capabilities that deliver immediate value and form the foundation for everything else.

#### 1. Financial Data Extraction & Structuring
- Extract key fields from **재무제표, 현금흐름표, 손익계산서, 부채현황표**
- Handle both structured tables and unstructured narrative sections
- Support for **Korean GAAP / K-IFRS** terminology normalization
- Output standardized JSON/CSV schemas for downstream processing
- Handle scanned PDFs via OCR (Korean text recognition)

#### 2. Automated Financial Ratio Calculation (20-30 ratios)

**Leverage Ratios:**
- 부채비율 (Debt-to-Equity), 부채/자산비율, 총부채/EBITDA

**Coverage Ratios:**
- 이자보상비율 (Interest Coverage = EBIT/Interest)
- DSCR (Debt Service Coverage Ratio) — critical for PF loans
- 고정비용보상비율

**Liquidity Ratios:**
- 유동비율 (Current Ratio), 당좌비율 (Quick Ratio)
- 현금류비율 (Cash Flow Ratio)

**Profitability:**
- 매출액영업이익률, 매출액순이익률, ROE, ROA, ROCE

**Efficiency:**
- 매출채권회전율 (DSO), 재고자산회전율 (DIO), 매입채무회전율 (DPO)

#### 3. Cross-Document Reconciliation
- Compare 대출신청서 revenue claims against 재무제표 매출액
- Verify 담보평가보고서 values against loan application collateral declarations
- Flag discrepancies automatically (e.g., "신청서 매출 50억 vs 재무제표 42억")
- Match AP/AR against bank statement flows

#### 4. Basic Trend Analysis (3-5 Years)
- YoY growth rates for revenue, EBITDA, net income
- Ratio trending with visual charts
- Deterioration alerts (e.g., "이자보상비율 3년 연속 하락")

#### 5. Rule-Based Risk Flagging
Configurable thresholds based on Korean banking credit policy:
- DSCR < 1.25× → 🔴 Critical
- Current Ratio < 1.0 → 🔴 Critical
- 부채비율 > 300% → 🟡 Warning
- 매출액 2년 연속 감소 → 🟡 Warning
- 이자보상비율 < 2× → 🟡 Warning
- 영업현금흐름 3년 연속 음수 → 🔴 Critical

#### 6. Automated Credit Memo Generation (Draft)
Generate draft 여신심사보고서 with:
- Borrower overview and industry classification
- Multi-year financial spreads (BS, P&L, CF tables)
- Calculated ratios with trend commentary
- Risk factors and mitigants
- Source citations for every extracted number (examiner-traceable)
- Recommended action (approve/decline/refer)

**Target:** Reduce memo writing from 4-8 hours to 30 minutes (analyst becomes editor)

#### 7. API-Ready Architecture
- RESTful endpoints: `/documents/upload`, `/analysis/{loan_id}`, `/memos/generate`, `/ratios/{loan_id}`, `/flags/{loan_id}`
- Webhook support for real-time triggers
- OAuth 2.0 authentication
- Audit logging for all operations

### 4.2 Tier 2: Phase 2 Enhancements (6-12 months)

| Capability | Description | Value |
|-----------|-------------|-------|
| **Multi-Entity Consolidation** | Handle complex structures (OPCO, HoldCo, RE LLCs); intercompany elimination; guarantor global CF analysis | Critical for middle-market and PF deals |
| **Covenant Testing & Compliance** | Track DSCR, leverage covenants; automated breach alerts; generate compliance reports | Separate revenue stream for portfolio monitoring |
| **Advanced Anomaly Detection** | ML-based outlier detection beyond simple thresholds; transaction pattern recognition; document forensics (tampering detection) | Catches subtle fraud patterns |
| **Scenario Analysis & Stress Testing** | Interest rate shock scenarios; revenue decline sensitivity; "what-if" covenant testing | Required for complex/large deals |
| **Deep LOS Integration** | Bidirectional sync with nCino, custom LOS, or Korean bank core systems; SSO; workflow triggers | Lock-in factor for enterprise adoption |

### 4.3 Tier 3: Future Roadmap (12+ months)

| Capability | Description |
|-----------|-------------|
| **Predictive Risk Scoring** | ML models for PD (Probability of Default) and LGD estimation; early warning signals |
| **Industry-Specific Benchmarks** | Peer group comparisons; industry percentile rankings; subsector-specific metrics |
| **Advanced Document Forensics** | AI-generated document detection; metadata tampering detection; revision history extraction |
| **Portfolio Analytics** | Portfolio-level risk aggregation; concentration analysis; CECL/IFRS 9 modeling integration |
| **Natural Language Query** | "이 회사의 현금흐름 악화 원인은?" — analyst asks questions in Korean, gets data-backed answers |

---

## 5. COMPLIANCE & SECURITY CONSIDERATIONS FOR KOREAN BANKS

### 5.1 Regulatory Framework (Must-Know)

Korean financial institutions operate under a strict regulatory environment for IT systems and data handling. A vendor solution must address the following:

#### A. Personal Information Protection Act (개인정보보호법, PIPA)
- **Applicability:** All corporate borrower data containing personally identifiable information (대표자 정보, 주주 정보 등) is subject to PIPA
- **Requirements:**
  - Explicit consent for data collection and processing
  - Purpose limitation (use data only for credit review, not marketing)
  - Data minimization (collect only necessary data)
  - Mandatory breach notification within 24 hours to authorities
  - Appointment of privacy officer (개인정보보호책임자)
  - Cross-border transfer restrictions (see data residency below)

#### B. Credit Information Act (신용정보법)
- **Applicability:** All credit applicant data, credit scores, and financial transaction data of borrowers
- **Requirements:**
  - Registration as a credit information provider if handling credit data
  - Strict access controls and usage logs
  - Prohibition of unauthorized credit inquiry
  - Data quality assurance obligations

#### C. ISMS-P (Information Security Management System – Personal Information)
- **Applicability:** Mandatory for financial companies and their IT vendors handling financial/personal data
- **Key Requirements:**
  - 399+ control items as specified by Financial Security Institute (금융보안원)
  - Applies to: Electronic Financial Transaction Act (전자금융거래법) and Credit Information Act entities
  - **Certification must be obtained BEFORE deployment**

### 5.2 Outsourcing Guidelines (금융회사 정보처리 업무 위탁 규정)

If a bank uses your tool as an outsourced data processing service:

| Requirement | Detail | Implication for Startup |
|-------------|--------|-------------------------|
| **Ex post facto reporting** | Banks must report outsourcing to FSC *after* signing contract (previously required pre-approval for EDPS) | Faster procurement; but vendor due diligence is rigorous |
| **Due diligence** | Banks must conduct risk assessment before outsourcing | Your company will face bank-level security audits |
| **Contract requirements** | Scope of work, data protection clauses, audit rights, liability, data ownership | You need a financial-grade MSA template |
| **Subcontracting** | Re-outsourcing allowed but same standards apply | If you use cloud providers, they must meet standards too |
| **Overseas outsourcing** | Special reporting required (30 business days advance notice for individual customer financial transaction data) | Avoid overseas data transfer for credit applicant data; use Korean data centers |

### 5.3 Cloud Usage & Data Residency

#### Current Status (as of 2026):
- **Korean banks CAN use cloud computing** for both front-office (essential) and back-office (non-essential) functions
- **SaaS exemptions:** FSC introduced rules in 2024-2026 allowing SaaS usage on internal networks without regulatory sandbox approval
  - BUT: SaaS must be pre-screened by Financial Security Institute (금융보안원)
  - Cannot handle **personal identification information** or **personal credit information** via exempted SaaS
  - Rigorous IT security protocols required (certification, authorization, access device controls)

#### Data Residency Requirements:
- **Corporate financial data:** Must be stored in Korea (on-premise or Korean cloud region)
- **Credit applicant personal data:** Strictly domestic storage; cross-border transfer requires explicit consent + FSC notification
- **AWS/GCP/Azure:** Korean regions (Seoul) are permitted IF vendor obtains K-ISMS/ISMS-P certification
- **Recommendation:** Use Korean cloud providers (Naver Cloud, Kakao Enterprise Cloud) or on-premise deployment for maximum bank acceptance

### 5.4 Network Separation Regulations (망분리)

- **Challenge:** Korean banks historically required physical network separation between internet-facing and internal systems
- **Recent change (2024-2026):** FSC granted exemptions for SaaS on internal networks IF:
  - Alternative information protection controls are implemented
  - Pre-screened by Financial Security Institute
  - Semi-annual compliance reports to CISO
- **Implication:** Your tool must support **on-premise deployment** or **private cloud within bank's network**; public SaaS is generally unacceptable for credit review data

### 5.5 Compliance Checklist for MVP

| # | Requirement | MVP Must Address |
|---|-------------|-----------------|
| 1 | **ISMS-P Certification** | Start certification process immediately; banks won't procure without it |
| 2 | **Data Residency (Korea-only)** | Deploy in Korean data centers; no cross-border data transfer |
| 3 | **Encryption at Rest & In Transit** | AES-256 encryption for stored data; TLS 1.3 for network communication |
| 4 | **Access Control & Audit Logs** | Role-based access control (RBAC); comprehensive audit trail of all data access |
| 5 | **PIPA Compliance** | Privacy notice; consent management; data retention/deletion policies |
| 6 | **Credit Information Act Compliance** | Access logs; purpose limitation; no unauthorized credit inquiries |
| 7 | **Business Continuity Plan** | Disaster recovery; backup procedures; SLA commitments |
| 8 | **Vendor Due Diligence Readiness** | Security questionnaires; penetration test reports; compliance documentation |
| 9 | **On-Premise Deployment Option** | Banks will require this; containerized deployment (Docker/K8s) is essential |
| 10 | **No Training Data Retention** | Clarify that borrower documents are NOT used to train LLMs; data isolation guarantees |

---

## 6. ACTIONABLE MVP ROADMAP

### Phase 1: Foundation (Months 1-3)
1. **Table Extraction Engine:**
   - Support PDF + HWP + scanned PDF (OCR)
   - Korean financial statement table recognition (대차대조표, 손익계산서, 현금흐름표)
   - Output structured JSON with K-GAAP/K-IFRS field normalization

2. **Semantic Search Layer:**
   - Vector DB (e.g., pgvector, Milvus, or Pinecone)
   - Document chunking optimized for financial tables
   - "담보가치 하락 추세", "DSCR 1.2 이하" — semantic + structured hybrid search

3. **Ratio Calculation Module:**
   - Implement 20 core ratios from extracted data
   - Multi-year calculation (extract 3 years from statements)
   - Simple rule-based flagging (5-10 threshold rules)

### Phase 2: Intelligence (Months 4-6)
4. **Cross-Document Reconciliation:**
   - Compare 대출신청서 vs 재무제표 values
   - Flag discrepancies with severity levels

5. **Trend Analysis Dashboard:**
   - Visual charts for 3-5 year trends
   - Deterioration alerts

6. **Draft Memo Generation:**
   - Korean-language credit memo template
   - Auto-populate spreads + ratios + flags
   - Source citations for examiner audit trail

7. **API & Integration Prep:**
   - REST API with auth
   - Webhook support
   - Containerized deployment for on-premise

### Phase 3: Compliance & Pilot (Months 7-9)
8. **ISMS-P Certification Process:**
   - Engage consultant (e.g., Financial Security Institute affiliate)
   - Implement all 399+ controls
   - Complete audit and obtain certification

9. **Pilot with 1-2 Regional Banks:**
   - Target: smaller regional banks (지방은행) with less internal IT resources
   - Use pilot to refine Korean-language UX and document format handling

10. **Security Hardening:**
    - Penetration testing
    - Data encryption verification
    - RBAC implementation
    - Audit logging

### Phase 4: Scale (Months 10-12)
11. **Enterprise Features:**
    - Multi-entity consolidation
    - Covenant tracking
    - LOS integration (custom connectors)

12. **Advanced AI Features:**
    - ML-based anomaly detection
    - Natural language query in Korean
    - Industry-specific benchmarking

---

## 7. KEY SUCCESS FACTORS

1. **Korean Document Fluency:** The tool must flawlessly handle Korean financial document formats, mixed Korean-English content, and typical bank template variations. This is your primary moat vs global competitors.

2. **Compliance-First Approach:** ISMS-P certification and on-premise deployment capability are non-negotiable for bank customers. Start compliance work early; it takes 3-6 months.

3. **Analyst-Centric UX:** The user is not a data scientist; they are a credit reviewer (여신심사역). The interface must feel like a faster, smarter version of their current Excel/Outlook workflow, not a radical new paradigm.

4. **Explainability:** Every AI output (ratios, flags, memo text) must have a traceable source document and page number. Korean banks and regulators demand explainability.

5. **Hybrid Approach (not pure LLM):** Shinhan's internal tool explicitly emphasizes NOT relying solely on LLMs. Combine rule-based financial logic (e.g., ratio formulas) with LLMs for narrative generation. This builds trust and reduces hallucination risk.

6. **Target Market Entry:** Start with **regional banks** or **savings banks** (저축은행) that have less internal AI capability but the same compliance requirements. They are more likely to buy vs build.

---

*Analysis compiled from Korean banking regulations (FSC, FSS, 금융보안원), industry reports, fintech competitive landscape research, and credit analysis best practices (CFA Institute, CRISIL, S&P Global).*
