# Requirement: Smart Search with LLM Re-ranking

## Problem Statement
The current PDF table search system relies solely on vector similarity search, which produces insufficient accuracy for large PDF documents. When searching for specific financial tables like "포괄손익계산서" (Statement of Comprehensive Income), the correct table appears in 5th position rather than 1st, indicating that semantic similarity alone cannot capture precise table identification requirements.

## Success Criteria
- **Primary**: The exact table "포괄손익계산서" appears in position 1 when searched
- **Secondary**: Overall search accuracy improves by 80%+ for financial table queries
- **Performance**: End-to-end search completes within 10 seconds for typical queries
- **Reliability**: System gracefully degrades when LLM API fails (fallback to vector search)
- **Compatibility**: Existing code and APIs remain functional (no breaking changes)

## Functional Requirements

### FR-1: Smart Search Core Functionality
**Description**: Implement `smart_search()` function that combines vector search with LLM re-ranking to identify the single most relevant table.

**Acceptance Criteria**:
- Returns exactly one `TableSearchResult` object (not a list)
- The result has the highest relevance score after LLM re-ranking
- Function signature matches the specification below
- Works with both Korean and English queries

**Interface**:
```python
def smart_search(
    query: str,
    pdf_path: str,
    top_k: int = 20,
    llm_model: str = "glm-5.1",
    api_key: Optional[str] = None,
    use_hybrid: bool = True,
    output_dir: Optional[str] = None,
    fallback_to_vector: bool = True,
) -> TableSearchResult:
    """
    Vector search + LLM re-ranking for precise table identification.
    
    Args:
        query: Natural language search query (Korean/English)
        pdf_path: Path to PDF document
        top_k: Number of candidates for LLM evaluation (default=20)
        llm_model: LLM model name (glm-5.1, glm-5.0)
        api_key: z.ai API key (falls back to ZAI_API_KEY env var)
        use_hybrid: Use hybrid mode for PDF processing
        output_dir: Override PDF conversion output directory
        fallback_to_vector: If True, return vector search result on LLM failure
    
    Returns:
        Single TableSearchResult with highest relevance
    
    Raises:
        TableSearchError: If search fails completely
        APIConnectionError: If LLM API unreachable and fallback disabled
    """
```

**Dependencies**:
- Existing `PDFTableSearch` class
- `TableVectorStore.similarity_search()` method
- `TableSearchResult` data model
- z.ai API connectivity

---

### FR-2: LLM Integration for Table Selection
**Description**: Implement LLM-based table selection that evaluates candidate tables and chooses the most relevant one.

**Acceptance Criteria**:
- Uses z.ai API (https://api.z.ai/api/coding/paas/v4 or compatible endpoint)
- Supports GLM-5.1 and GLM-5.0 models
- Sends table titles and content previews to LLM
- Receives structured response with selected table index
- Handles API errors gracefully with retry logic

**LLM Prompt Structure**:
```python
_SMART_SEARCH_PROMPT = """You are a financial table search expert. Given a user query and a list of tables from a financial report, select the single most relevant table.

User Query: {query}

Available Tables:
{table_descriptions}

Instructions:
1. Analyze the user's search intent
2. Match against table titles and content
3. Consider Korean financial terminology
4. Select the ONE table that best matches the query

Respond with ONLY a JSON object:
{{
  "selected_index": <1-based index of best table>,
  "confidence": <0.0 to 1.0>,
  "reasoning": "<brief explanation in Korean>"
}}"""
```

**Dependencies**:
- Valid z.ai API key
- Network connectivity to z.ai endpoint
- Error handling infrastructure

---

### FR-3: Candidate Preparation for LLM
**Description**: Format candidate tables from vector search into clear, structured descriptions for LLM evaluation.

**Acceptance Criteria**:
- Includes table title (if available)
- Includes page number for reference
- Includes content preview (first 300-500 chars)
- Uses clear numbering (1, 2, 3...) for LLM reference
- Handles tables without titles gracefully

**Table Description Format**:
```
Table 1 (Page 12)
Title: 포괄손익계산서
Content: | 계정 | 당기 | 전기 |
| 매출액 | 1,234,567 | 987,654 |
...

Table 2 (Page 8)
Title: 재무상태표
Content: | 계정 | 당기 | 전기 |
...
```

**Dependencies**:
- `TableSearchResult` objects from vector search
- Metadata includes table_title, page_number, table_markdown

---

### FR-4: CLI Interface for Testing
**Description**: Create a command-line interface for testing smart_search functionality.

**Acceptance Criteria**:
- Executable via `python -m pdftablesearch.smart_search_cli`
- Supports required parameters: `--pdf`, `--query`
- Supports optional parameters: `--top-k`, `--llm-model`, `--api-key`, `--output-dir`
- Prints result in human-readable format
- Shows selected table details (ID, page, title, preview)

**CLI Usage**:
```bash
python -m pdftablesearch.smart_search_cli \
  --pdf test2.pdf \
  --query "포괄손익계산서" \
  --top-k 20 \
  --llm-model glm-5.1
```

**Expected Output**:
```
🔍 Smart Search Results
========================
Query: 포괄손익계산서
PDF: test2.pdf

✅ Best Match Found:
  Table ID: table_12_3
  Page: 12
  Title: 포괄손익계산서
  Confidence: 0.95
  
  Preview:
  | 계정 | 당기 | 전기 |
  |-----|------|------|
  | 매출액 | 1,234,567 | 987,654 |
...
```

**Dependencies**:
- argparse or click for CLI parsing
- smart_search function implementation

---

### FR-5: Error Handling and Fallback
**Description**: Implement robust error handling with graceful degradation when LLM API fails.

**Acceptance Criteria**:
- Retries transient failures (rate limits, network issues)
- Falls back to vector search top result if LLM fails completely
- Logs all failures with context
- Raises exception only if both LLM and fallback fail
- Supports configurable fallback behavior

**Error Handling Flow**:
```
1. Vector search (top_k=20) → Get candidates
2. LLM API call:
   a. On success → Parse response → Return selected table
   b. On transient error (rate limit, timeout):
      - Retry with exponential backoff (max 3 attempts)
      - If all retries fail → Go to step 2c
   c. On fatal error (auth failure, invalid response):
      - If fallback_to_vector=True → Return vector search #1
      - If fallback_to_vector=False → Raise TableSearchError
```

**Dependencies**:
- Existing exception hierarchy (APIError, RateLimitError, etc.)
- Retry configuration utilities

---

### FR-6: Integration with Existing Code
**Description**: Ensure smart_search integrates seamlessly with existing PDFTableSearch class architecture.

**Acceptance Criteria**:
- Can be called as method on PDFTableSearch class
- Reuses existing vector store and embeddings
- Uses existing TableSearchResult model
- Compatible with existing caching mechanisms
- No changes required to existing search() method

**Integration Point**:
```python
class PDFTableSearch:
    # ... existing methods ...
    
    def smart_search(
        self,
        pdf_path: str,
        query: str,
        top_k: int = 20,
        llm_model: str = "glm-5.1",
        fallback_to_vector: bool = True,
    ) -> TableSearchResult:
        """Add smart_search as a class method for convenience."""
        # Implementation
```

**Dependencies**:
- Existing PDFTableSearch infrastructure
- Existing document caching and vector store management

---

## Technical Considerations

### Architecture Impact
- **New Module**: `pdftablesearch/smart_search.py` (core logic)
- **CLI Module**: `pdftablesearch/smart_search_cli.py` (command-line interface)
- **Extension**: Add `smart_search()` method to `PDFTableSearch` class
- **No Breaking Changes**: Existing APIs remain unchanged

### Performance Requirements
- **Vector Search**: < 2 seconds for top_k=20
- **LLM API Call**: < 5 seconds (including retries)
- **Total Time**: < 10 seconds end-to-end
- **Memory**: Minimal additional memory (reuses existing vector store)

### API Configuration
- **Endpoint**: https://api.z.ai/api/coding/paas/v4 (OpenAI-compatible)
- **Models**: glm-5.1 (primary), glm-5.0 (fallback option)
- **Auth**: Bearer token via API key
- **Timeout**: 30 seconds default
- **Retries**: 3 attempts with exponential backoff

### Error Handling Strategy
1. **Vector Search Fails**: Raise VectorSearchError (existing behavior)
2. **LLM API Transient Failure**: Retry with backoff, then fallback
3. **LLM API Fatal Failure**: Fallback to vector or raise exception
4. **Response Parse Failure**: Log warning, fallback to vector
5. **No Candidates**: Return empty result or raise based on configuration

### LLM Response Format
```json
{
  "selected_index": 3,
  "confidence": 0.95,
  "reasoning": "사용자가 '포괄손익계산서'를 검색했으며, 테이블 3의 제목이 정확히 일치합니다."
}
```

### Prompt Engineering Guidelines
- Use Korean for reasoning and explanations
- Provide clear, structured input
- Request JSON output for reliable parsing
- Include examples in system prompt if needed
- Handle edge cases (no title, ambiguous queries)

---

## Clarifications Needed

### Q1: LLM API Endpoint Compatibility
**Issue**: The existing `ZaiRerankCompressor` uses a different endpoint (`https://api.z.ai/api/coding/paas/v4`) than the user mentioned (`https://open.bigmodel.cn/`).

**Why This Matters**: Determines whether we can reuse existing LLM integration code or need a new client implementation.

**Options**:
1. Use existing endpoint (proven to work with codebase)
2. Use new endpoint (requires testing, may have different API)
3. Support both endpoints with configuration

**Recommendation**: Verify with user which endpoint to use. If `https://open.bigmodel.cn/` is correct, test its API compatibility first.

---

### Q2: LLM Response Format Preference
**Issue**: Should the LLM return:
- Option A: JSON only (machine-readable, easier parsing)
- Option B: Natural language + JSON (human-interpretable, more robust)
- Option C: Natural language only (requires regex parsing)

**Why This Matters**: Affects prompt design and response parsing reliability.

**Recommendation**: Use JSON-only response for reliability, but include a "reasoning" field in Korean for debugging and transparency.

---

### Q3: Fallback Strategy Granularity
**Issue**: Current spec has binary fallback (on/off). Should we support:
- Option A: Binary fallback (current design)
- Option B: Return both LLM result and vector result for comparison
- Option C: Return top-3 LLM candidates instead of single best

**Why This Matters**: Affects API design and user experience for edge cases.

**Recommendation**: Start with binary fallback for simplicity. Can extend to Option B in future for A/B testing capabilities.

---

### Q4: API Key Management Scope
**Issue**: Should smart_search use:
- Option A: Same `ZAI_API_KEY` environment variable as existing code
- Option B: Separate `SMART_SEARCH_API_KEY` for isolation
- Option C: Support both with precedence

**Why This Matters**: Affects configuration complexity and cost tracking.

**Recommendation**: Use `ZAI_API_KEY` for consistency, but document that smart_search may have different cost characteristics.

---

### Q5: Token Limit Handling
**Issue**: Large PDFs may produce table descriptions that exceed LLM context windows.

**Why This Matters**: Need strategy for handling very large candidate sets.

**Options**:
1. Truncate table descriptions aggressively
2. Batch LLM calls (10 tables per call)
3. Use hierarchical approach (LLM filters → LLM selects)
4. Limit top_k to safe maximum (e.g., 20)

**Recommendation**: Start with top_k=20 limit and aggressive truncation. Monitor actual token usage and adjust.

---

## Recommended Next Steps

### Phase 1: Foundation (Week 1)
1. **Verify LLM API Access**: Test both endpoints to determine correct API configuration
2. **Create Core Module**: Implement `smart_search()` function with vector search integration
3. **Implement LLM Client**: Create z.ai API client with retry logic
4. **Basic Prompt Engineering**: Develop initial prompt template

### Phase 2: Integration (Week 1-2)
5. **Add CLI Interface**: Create `smart_search_cli.py` for testing
6. **Integrate with PDFTableSearch**: Add as class method
7. **Implement Error Handling**: Add fallback logic and comprehensive error handling
8. **Unit Tests**: Write tests for core functionality

### Phase 3: Refinement (Week 2)
9. **Prompt Optimization**: Test and refine prompts with real queries
10. **Performance Tuning**: Optimize token usage and response times
11. **Documentation**: Add docstrings and usage examples
12. **Integration Testing**: Test with real financial PDFs

### Phase 4: Validation (Week 2-3)
13. **Accuracy Testing**: Measure improvement over vector-only search
14. **Edge Case Handling**: Test ambiguous queries, missing titles, etc.
15. **Performance Benchmarking**: Validate response time requirements
16. **Production Readiness**: Final error handling and logging

---

## Implementation Notes

### File Structure
```
pdftablesearch/
├── smart_search.py          # NEW: Core smart_search function
├── smart_search_cli.py      # NEW: CLI interface
├── search.py                # MODIFY: Add smart_search() method to PDFTableSearch
├── llm_client.py            # NEW: Optional dedicated LLM client
└── __init__.py              # MODIFY: Export smart_search function
```

### Dependencies to Add
```python
# No new dependencies required
# Uses existing:
# - langchain_openai (ChatOpenAI)
# - requests (HTTP client)
# - tenacity (retry logic)
```

### Configuration Environment Variables
```bash
# Existing (will reuse)
ZAI_API_KEY=your_api_key_here

# New (optional)
SMART_SEARCH_DEFAULT_MODEL=glm-5.1
SMART_SEARCH_DEFAULT_TOP_K=20
SMART_SEARCH_TIMEOUT=30
SMART_SEARCH_ENABLE_FALLBACK=true
```

### Testing Strategy
1. **Unit Tests**: Mock LLM API responses, test vector search integration
2. **Integration Tests**: Test with real LLM API (use small test PDFs)
3. **Accuracy Tests**: Compare results with/without smart_search
4. **Performance Tests**: Measure response times under load

---

## Success Metrics

### Quantitative Metrics
- **Accuracy Improvement**: Target 80%+ improvement in position-1 accuracy
- **Response Time**: 95th percentile < 10 seconds
- **API Success Rate**: >95% (after retries)
- **Fallback Rate**: <10% (indicates LLM reliability)

### Qualitative Metrics
- **User Satisfaction**: Correct table appears in top 3 for financial queries
- **Debugging**: Clear logging and error messages
- **Maintainability**: Code follows existing patterns and conventions
- **Documentation**: Clear usage examples and API documentation

---

## Risk Mitigation

### Risk 1: LLM API Unreliability
**Mitigation**: Comprehensive retry logic + fallback to vector search

### Risk 2: High API Costs
**Mitigation**: Cache frequent queries, limit top_k, monitor token usage

### Risk 3: Poor LLM Accuracy
**Mitigation**: Prompt engineering, A/B testing, fallback to vector search

### Risk 4: Performance Degradation
**Mitigation**: Parallel vector/LLM processing, caching, timeout limits

### Risk 5: Breaking Existing Code
**Mitigation**: Additive changes only, no modifications to existing APIs

---

This requirements document provides a complete foundation for implementing the smart_search feature. All functional requirements are specified with acceptance criteria, technical considerations are detailed, and clarifications are explicitly flagged for user input before implementation begins.
