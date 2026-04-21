# Smart Search Architecture Overview

## System Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Query                              │
│                    "포괄손익계산서"                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    smart_search()                               │
│                  (Entry Point)                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
┌───────────────────────┐     ┌──────────────────────────┐
│  Phase 1: Vector      │     │  Phase 2: LLM Re-ranking │
│  Search               │     │                         │
│                       │     │  - Get top_k=20 tables   │
│  - Query embedding    │────▶│  - Prepare descriptions  │
│  - Similarity search  │     │  - Call z.ai API         │
│  - Return candidates  │     │  - Select best match     │
└───────────────────────┘     └───────────┬──────────────┘
                                          │
                             ┌────────────┴────────────┐
                             │                         │
                    Success? │                   Failure?
                             ▼                         ▼
                  ┌──────────────────┐      ┌─────────────────┐
                  │ Return selected  │      │ Fallback to     │
                  │ TableSearchResult│      │ vector #1       │
                  └──────────────────┘      └─────────────────┘
```

## Component Architecture

```
pdftablesearch/
├── smart_search.py              # NEW: Core smart_search logic
│   ├── smart_search()           # Main function
│   ├── _prepare_candidates()    # Format tables for LLM
│   ├── _call_llm_selection()    # z.ai API integration
│   └── _parse_llm_response()    # Extract selection from response
│
├── smart_search_cli.py          # NEW: Command-line interface
│   └── main()                   # CLI entry point
│
├── search.py                    # MODIFY: Add method to PDFTableSearch
│   └── PDFTableSearch.smart_search()
│
├── llm_client.py                # NEW: Optional dedicated LLM client
│   ├── ZaiLLMClient            # z.ai API wrapper
│   └── _build_selection_prompt()
│
└── models.py                    # EXISTING: Reuse TableSearchResult
    └── TableSearchResult        # Single result output
```

## Data Flow

### Input
```python
smart_search(
    query="포괄손익계산서",
    pdf_path="test2.pdf",
    top_k=20,
    llm_model="glm-5.1"
)
```

### Phase 1: Vector Search
```python
# Returns 20 candidates
candidates = vector_store.similarity_search(
    query="포괄손익계산서",
    k=20
)

# Example candidate:
TableSearchResult(
    table_id="table_12_3",
    page_number=12,
    table_title="포괄손익계산서",
    relevance_score=0.72,  # Vector similarity
    table_markdown="| 계정 | ..."
)
```

### Phase 2: LLM Selection
```python
# Prepare descriptions for LLM
descriptions = _prepare_candidates(candidates)
"""
Table 1 (Page 8)
Title: 재무상태표
Content: | 자산 | 금액 | ...

Table 2 (Page 12)
Title: 포괄손익계산서
Content: | 계정 | 당기 | 전기 | ...
...
"""

# Call LLM
response = llm_client.select_table(
    query="포괄손익계산서",
    descriptions=descriptions
)

# LLM Response
{
  "selected_index": 2,  # 0-based index
  "confidence": 0.95,
  "reasoning": "사용자가 '포괄손익계산서'를 검색했으며, 테이블 2의 제목이 정확히 일치합니다."
}
```

### Output
```python
# Return single best result
TableSearchResult(
    table_id="table_12_3",
    page_number=12,
    table_title="포괄손익계산서",
    relevance_score=0.72,
    rerank_score=0.95,  # NEW: LLM confidence
    table_markdown="| 계정 | ..."
)
```

## Error Handling Flow

```
┌─────────────────────────────────────────────────────────┐
│                  smart_search()                         │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────┐          ┌──────────────┐
│ Vector Search│          │  LLM API     │
│   Fails      │          │   Fails      │
└──────┬───────┘          └──────┬───────┘
       │                         │
       │                  ┌──────┴──────┐
       │                  │             │
       │             Transient    Fatal Error
       │                │             │
       │             Retry          │
       │           (3 times)        │
       │                │             │
       │             ┌──┴──┐         │
       │             │     │         │
       │          Success   Fail     │
       │             │     │         │
       ▼             ▼     ▼         ▼
┌─────────────┐ ┌─────┐ ┌─────┐ ┌───────────┐
│ Raise       │ │Cont.│ │Fall.│ │ Raise or  │
│VectorSearch │ │LLM  │ │Back │ │ Fallback  │
│   Error     │ │     │ │     │ │           │
└─────────────┘ └─────┘ └─────┘ └───────────┘
```

## API Integration Points

### z.ai API (ChatOpenAI)
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="https://api.z.ai/api/coding/paas/v4",
    api_key=os.getenv("ZAI_API_KEY"),
    model="glm-5.1",
    temperature=0.1,
    request_timeout=30
)
```

### Existing Components
```python
# Reuse PDFTableSearch infrastructure
searcher = PDFTableSearch()

# Reuse vector store
vector_store = TableVectorStore(embeddings=searcher.embeddings)

# Reuse result model
result = TableSearchResult.from_langchain_document(doc, score)
```

## Performance Considerations

### Bottlenecks
1. **Vector Search**: ~1-2 seconds (already optimized)
2. **LLM API Call**: ~3-5 seconds (network + inference)
3. **Response Parsing**: <100ms (trivial)

### Optimization Strategies
- **Caching**: Cache frequent query → result mappings
- **Parallel Processing**: Can't parallelize (LLM depends on vector results)
- **Batch Processing**: Future: Process multiple queries in single LLM call
- **Token Optimization**: Truncate table descriptions to reduce tokens

### Cost Considerations
- **Input Tokens**: ~1000-2000 tokens per query (depends on top_k)
- **Output Tokens**: ~100 tokens per response
- **Estimated Cost**: $0.01-0.05 per query (verify with z.ai pricing)

## Testing Strategy

### Unit Tests
```python
# Test candidate preparation
def test_prepare_candidates():
    candidates = [mock_table_1, mock_table_2]
    descriptions = _prepare_candidates(candidates)
    assert "Table 1" in descriptions
    assert "Table 2" in descriptions

# Test response parsing
def test_parse_llm_response():
    response = '{"selected_index": 2, "confidence": 0.95}'
    result = _parse_llm_response(response)
    assert result['selected_index'] == 2
```

### Integration Tests
```python
# Test full flow with mock LLM
def test_smart_search_with_mock():
    with mock_llm_response(selected_index=1):
        result = smart_search("query", "test.pdf")
        assert result.table_id == "table_X_Y"

# Test fallback
def test_smart_search_fallback():
    with mock_llm_failure():
        result = smart_search("query", "test.pdf", fallback=True)
        assert result is not None  # Got vector fallback
```

### Accuracy Tests
```python
# Test with real queries
queries = [
    ("포괄손익계산서", "table_12_3"),
    ("재무상태표", "table_8_1"),
    ("현금흐름표", "table_15_2"),
]

for query, expected_table in queries:
    result = smart_search(query, "financial_report.pdf")
    assert result.table_id == expected_table
```

## Deployment Checklist

- [ ] Verify z.ai API access and credentials
- [ ] Test with sample financial PDFs
- [ ] Benchmark accuracy improvement
- [ ] Measure response times
- [ ] Configure monitoring and logging
- [ ] Set up cost tracking
- [ ] Document API usage patterns
- [ ] Create user guide and examples
- [ ] Train users on new functionality
- [ ] Plan for API rate limiting
