# Scout: AI Engineer Learning Plan

## Overview

A comprehensive roadmap to master AI engineering through building a job search assistant with RAG, evaluation harness, and production agent patterns.

---

## Phase 1: RAG for Job Matching (Week 1-2)

### Goal
Semantic job matching using embeddings

### Architecture
```
Job Postings → Embeddings → Vector DB → Semantic Search → Match Results
                    ↓
            User Skills → Embeddings → Similarity Scoring
```

### Tech Stack
| Component | Choice | Why |
|-----------|--------|-----|
| Vector DB | **pgvector** | Already have PostgreSQL |
| Embedding Model | **OpenAI text-embedding-3-small** | Easy integration, good quality |
| Reranker | **BAAI/bge-reranker-v2-m3** | Open-source, high quality |

### Files to Create
```
app/rag/
├── __init__.py
├── embeddings.py      # Embedding generation
├── vector_store.py    # pgvector operations
├── retriever.py       # Hybrid search + reranking
└── matcher.py         # Job-candidate matching
```

### Key Skills
- Embedding generation and storage
- Vector similarity search
- Hybrid retrieval (BM25 + dense)
- Cross-encoder reranking
- Semantic chunking for job postings

---

## Phase 2: Evaluation Harness (Week 2-3)

### Goal
Measure and improve agent quality systematically

### Architecture
```
Test Cases → Agent Output → LLM Judge → Scores → Report
                ↓
          Human Review → Calibration
```

### Tech Stack
| Component | Choice | Why |
|-----------|--------|-----|
| Eval Framework | **DeepEval** | pytest-native, 50+ metrics |
| RAG Metrics | **RAGAS** | RAG-specific evaluation |
| Observability | **LangSmith** | Tracing + eval |

### Files to Create
```
tests/eval/
├── __init__.py
├── judge.py           # LLM-as-judge scoring
├── metrics.py         # Custom metrics
├── fixtures/          # Test data
│   ├── jobs.json
│   ├── companies.json
│   └── expected_cover_letters.json
└── test_agents.py     # Agent quality tests

scripts/
└── eval.py            # Run evaluations
```

### Metrics
| Agent | Metric | How to Measure |
|-------|--------|----------------|
| Cover Letter | Relevance | LLM judge: does it match job requirements? |
| Cover Letter | Skill Match | Check if user skills appear in letter |
| Research | Completeness | Are all fields populated? |
| Research | Accuracy | Compare against known company data |
| RAG | Faithfulness | Is answer grounded in retrieved context? |
| RAG | Context Precision | Are retrieved contexts ranked correctly? |

### Key Skills
- LLM-as-judge pattern
- Custom evaluation criteria
- Prompt quality measurement
- Regression testing for AI
- A/B testing prompts

---

## Phase 3: Agent Architecture Improvements (Week 3-4)

### Goal
Production-ready agent patterns

### Improvements
| Area | Current | Improved |
|------|---------|----------|
| State | Untyped dict | TypedDict/Pydantic |
| Checkpointing | None | PostgresSaver |
| Error Handling | Basic try/catch | Retry policies + LLM recovery |
| HITL | None | Approval gates for emails |

### Files to Modify
```
app/agents/
├── pipeline.py           # Add TypedDict state, checkpointing
├── error_handler.py      # NEW: Retry + recovery patterns
└── approval.py           # NEW: Human-in-the-loop gates
```

### Key Skills
- LangGraph TypedDict state
- Checkpointing with PostgresSaver
- Retry policies with backoff
- LLM-guided error recovery
- Human-in-the-loop with interrupt()

---

## Phase 4: Prompt Engineering Mastery (Week 4-5)

### Goal
Systematic prompt optimization

### Patterns
| Pattern | Where to Apply |
|---------|----------------|
| Chain-of-Thought | Job matching analysis |
| Structured Output | Cover letter, company research |
| Few-Shot Examples | Skill extraction, match scoring |
| Prompt Versioning | All prompts with eval gates |

### Files to Create
```
app/prompts/
├── __init__.py
├── cover_letter.py       # Versioned cover letter prompts
├── research.py           # Versioned research prompts
├── matching.py           # Versioned matching prompts
└── versions.py           # Version registry
```

### Key Skills
- Chain-of-thought prompting
- Structured outputs (OpenAI JSON mode)
- Dynamic few-shot selection
- Prompt versioning and A/B testing
- Eval-driven prompt optimization

---

## Complete File Structure After Implementation

```
scout/
├── app/
│   ├── agents/
│   │   ├── cover_letter.py
│   │   ├── researcher.py
│   │   ├── scraper.py
│   │   ├── pipeline.py        # UPDATED: TypedDict state
│   │   ├── error_handler.py   # NEW
│   │   └── approval.py        # NEW
│   ├── rag/
│   │   ├── embeddings.py      # NEW
│   │   ├── vector_store.py    # NEW
│   │   ├── retriever.py       # NEW
│   │   └── matcher.py         # NEW
│   ├── prompts/
│   │   ├── cover_letter.py    # NEW
│   │   ├── research.py        # NEW
│   │   ├── matching.py        # NEW
│   │   └── versions.py        # NEW
│   ├── api/
│   │   └── routes.py          # UPDATED: new endpoints
│   └── config.py
├── tests/
│   ├── eval/
│   │   ├── judge.py           # NEW
│   │   ├── metrics.py         # NEW
│   │   ├── fixtures/          # NEW
│   │   └── test_agents.py     # NEW
│   └── ...
└── scripts/
    └── eval.py                # NEW
```

---

## Learning Outcomes

| Skill | Experience |
|-------|------------|
| **RAG** | Built semantic job matching with pgvector |
| **Evaluation** | Implemented LLM-as-judge with DeepEval |
| **Agent Architecture** | Production LangGraph with checkpointing |
| **Prompt Engineering** | Versioned prompts with eval gates |
| **Production AI** | Error handling, HITL, monitoring |

---

## Recommended Tech Stack Summary

| Component | Development | Production |
|-----------|-------------|------------|
| Vector DB | Chroma (embedded) | Qdrant Cloud or pgvector |
| Embedding Model | BAAI/bge-small-en-v1.5 | OpenAI text-embedding-3-large |
| Reranker | BAAI/bge-reranker-v2-m3 | Cohere Rerank |
| LLM Framework | LangChain + LangGraph | LangGraph with PostgresSaver |
| Evaluation | DeepEval (CI) + RAGAS (RAG) | DeepEval + Phoenix |
| Structured Output | OpenAI structured outputs | Same, with Pydantic validation |
| Prompt Versioning | File-based with version registry | Same, with eval gates in CI |

---

## Resources

- **DeepEval**: https://github.com/confident-ai/deepeval
- **RAGAS**: https://github.com/explodinggradients/ragas
- **LangGraph**: https://github.com/langchain-ai/langgraph
- **Chroma**: https://docs.trychroma.com
- **Qdrant**: https://qdrant.tech/documentation
- **pgvector**: https://github.com/pgvector/pgvector
- **Arize Phoenix**: https://github.com/Arize-ai/phoenix
- **LangChain Academy**: https://www.langchain.com/langgraph
