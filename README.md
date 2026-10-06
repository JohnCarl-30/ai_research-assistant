# AI Research Assistant

An AI-powered job search assistant that monitors job boards, researches companies, and generates personalized cover letters using LangChain, LangGraph, and OpenAI.

## Features

- **Job Board Monitoring** - Scrape LinkedIn and Indeed for job opportunities
- **Company Research** - AI-powered analysis of company mission, tech stack, and culture
- **GitHub Signals** - Real tech stack and activity from the company's public GitHub org, via the GitHub MCP server
- **Claude Desktop Extension & Claude Code Plugin** - Keyless company research for anyone, running locally ([extension/](extension/README.md))
- **Cover Letter Generation** - Personalized cover letters based on your skills and job requirements
- **RAG-Based Matching** - Semantic job matching using vector embeddings
- **Evaluation Harness** - LLM-as-judge quality measurement for all agents

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI |
| AI Orchestration | LangChain + LangGraph |
| LLM | OpenAI (GPT-4o-mini) |
| Monitoring | LangSmith |
| Database | PostgreSQL + pgvector |
| Embeddings | OpenAI text-embedding-3-small |
| Scraping | BeautifulSoup + httpx |

## Project Structure

```
scout/
├── app/
│   ├── agents/
│   │   ├── cover_letter.py    # Cover letter generation
│   │   ├── researcher.py      # Company research
│   │   ├── scraper.py         # Job board scraping
│   │   └── pipeline.py        # LangGraph workflow
│   ├── rag/
│   │   ├── chunking.py        # Job posting → self-contained chunks
│   │   ├── embeddings.py      # Embedding generation
│   │   ├── vector_store.py    # pgvector storage + similarity search
│   │   ├── retriever.py       # Hybrid search (dense + BM25, RRF fusion)
│   │   ├── qa.py              # Grounded question answering
│   │   └── matcher.py         # Job-candidate matching
│   ├── api/
│   │   └── routes.py          # API endpoints
│   ├── config.py              # Settings
│   ├── database.py            # PostgreSQL
│   └── main.py                # FastAPI app
├── tests/
│   ├── eval/
│   │   ├── harness.py         # Ragas evaluation harness
│   │   ├── ragas_compat.py    # Import shim (ragas#2753)
│   │   ├── test_rag_ragas.py  # Quality gate (opt-in)
│   │   └── fixtures/          # Eval corpus + golden questions
│   └── ...
├── scripts/
│   └── eval.py                # Run the evaluation, print a report
├── docker-compose.yml         # PostgreSQL + pgvector
└── pyproject.toml             # Dependencies
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL)
- OpenAI API key
- LangSmith API key (optional)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ai_research-assistant.git
cd ai_research-assistant

# Install dependencies
uv sync

# Start PostgreSQL
docker compose up -d

# Create .env file
cp .env.example .env
# Edit .env with your API keys

# Run the server
uv run uvicorn app.main:app --reload
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/health` | API status |
| GET | `/scan?query=python&location=remote&skills=Python,FastAPI` | Scan job boards + research companies + generate cover letters |
| GET | `/cover-letter?job_title=X&company_name=Y&skills=Z` | Generate a single cover letter |
| POST | `/api/rag/index` | Embed job postings into the vector store |
| GET | `/api/rag/search?q=...&top_k=5` | Retrieve job-posting chunks relevant to a query |
| POST | `/api/rag/ask` | Answer a question grounded in the indexed postings |
| POST | `/api/rag/match` | Rank indexed jobs against a skill profile |

### Example Usage

```bash
# Full pipeline: scrape jobs + research companies + generate cover letters
curl "http://localhost:8000/scan?query=python+developer&location=remote&skills=Python,FastAPI,React,LangChain"

# Generate a single cover letter
curl "http://localhost:8000/cover-letter?job_title=Python+Developer&company_name=Google&skills=Python,FastAPI,React"

# Index scraped jobs for retrieval (the /scan pipeline also does this automatically)
curl -X POST http://localhost:8000/api/rag/index -H 'Content-Type: application/json' -d '{"limit": 100}'

# Semantic + keyword search over indexed postings
curl "http://localhost:8000/api/rag/search?q=rust+systems+role+in+europe&top_k=5"

# Ask a grounded question
curl -X POST http://localhost:8000/api/rag/ask -H 'Content-Type: application/json' \
  -d '{"question": "Which roles are remote and do not require Kubernetes?"}'

# Rank jobs against your skills
curl -X POST http://localhost:8000/api/rag/match -H 'Content-Type: application/json' \
  -d '{"skills": ["python", "postgresql", "fastapi"], "role": "backend engineer"}'
```

## RAG

Job postings are chunked (each chunk keeps a title/company/location/salary header so
it stands alone), embedded with `text-embedding-3-small`, and stored in `job_chunks`.

Retrieval is hybrid. A dense arm searches pgvector by cosine distance; a sparse arm
runs BM25 over chunks matching any query term. The two ranked lists are combined with
reciprocal rank fusion, because cosine similarity and BM25 scores are not on comparable
scales. Dense alone misses exact tokens (a query for "Rust" otherwise pulls in Go
postings); BM25 alone misses paraphrase.

`/api/rag/ask` answers strictly from retrieved chunks and refuses when they do not
contain the answer — that constraint is what makes the faithfulness metric meaningful.

## GitHub research

When `GITHUB_TOKEN` is set, company research also reads the company's public GitHub
organisation through the remote GitHub MCP server. The implementation lives in
`extension/src/scout_mcp/github.py`, shared with the desktop extension, and
`app/agents/github_research.py` configures it from `Settings`:

1. Guess org logins from the company name (and domain, when known), and take the first
   that has repos: `search_repositories` with `org:<login>`, sorted by stars.
2. Count repo languages across the top 10 non-fork repos.
3. For the top 3 repos, list the root and read any dependency manifests
   (`package.json`, `pyproject.toml`, `requirements.txt`, `go.mod`, `Cargo.toml`, `Gemfile`)
   to find frameworks.

The result goes into the research prompt as evidence for `tech_stack`. It carries a match
confidence: `high` when a repo homepage is on the company's domain, `medium` when the
login came from the domain, and `low` when it was only guessed from the name. A `low`
match may be a different company with a similar name.

It is deterministic (no LLM calls) and read-only. The session is opened with the server's
read-only header, and the client refuses any tool other than `search_repositories` and
`get_file_contents`. A fine-grained token with public-repository read access is enough.
Without a token, or if the server can't be reached, research runs as before.

## Claude Desktop extension and Claude Code plugin

`extension/` packages Scout's company research as a one-click Claude Desktop
extension (`.mcpb`) and as a Claude Code plugin, so anyone can install it. It runs on
the user's computer, uses their own Claude, and needs no server, database or API keys
of any kind. Ask Claude about a company and the `research_company` tool builds a
dossier from keyless public sources: Wikidata facts, the website's tech stack, DNS
(email and SaaS tools), public job boards (hiring and the technologies job posts
name), GitHub, Hacker News and previously saved notes. Claude adds news with its own
web search and writes a cited brief. Notes are kept in a local SQLite file.

In Claude Code:

```
/plugin marketplace add <owner>/ai_research-assistant
/plugin install scout@scout-plugins
/scout:research-company Linear
```

Replace `<owner>` with the GitHub account or organisation that hosts this
repository.

It is a standalone package (`scout-mcp`). The backend depends on it for the shared
GitHub code, and it never depends on the backend. See [extension/README.md](extension/README.md)
to install, build and test it.

## Configuration

Create a `.env` file with the following variables:

```env
# OpenAI
OPENAI_API_KEY=sk-your-key-here

# LangSmith (optional)
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_PROJECT=ai-research-assistant

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/scout

# Gmail SMTP (for email notifications)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_RECIPIENT=your-email@gmail.com

# GitHub research (optional, read-only public-repo token)
GITHUB_TOKEN=github_pat_...
```

## Development

### Running Tests

```bash
# Unit tests — fast, no network, no API key needed
uv run pytest

# With coverage
uv run pytest --cov=app
```

### Evaluation

The RAG pipeline is scored with [ragas](https://github.com/explodinggradients/ragas)
against a fixed corpus in `tests/eval/fixtures/`. Both entry points make real OpenAI
calls (embeddings, one answer per question, several judge calls per metric), so they
are opt-in and excluded from the default test run.

```bash
# Report: per-metric scores against their floors, plus every Q/A pair
uv run python scripts/eval.py
uv run python scripts/eval.py --top-k 8 --json results.json

# Same evaluation as a pass/fail quality gate
RUN_EVAL=1 uv run pytest tests/eval -v
```

The gate has two tiers, split by cost rather than by importance:

```bash
# Cheap tier (~16s): retrieval only. Embeds the corpus and one vector per
# question, then stops — no answer generation, no judge. This catches the
# regression that matters most, because if retrieval stops finding the right
# postings then every judged metric downstream is scoring a broken retriever.
uv run python scripts/eval_gate.py --retrieval-only

# Full tier: agent regressions plus the four judged RAG metrics.
uv run python scripts/eval_gate.py --ragas
```

**Both tiers are local, pre-merge steps. CI does not run them and no OpenAI key
is configured there.** Every tier calls OpenAI — even the cheap one embeds — so
running them in CI would bill real money on each push, in a public repo where
anyone can open a pull request. CI runs the offline unit suite only, which needs
no key: `tests/conftest.py` defaults a placeholder so collection succeeds, and
`tests/eval` stays behind its `RUN_EVAL` guard.

Metrics: **faithfulness** (is the answer grounded in the retrieved context?),
**answer relevancy**, **context precision** (are relevant chunks ranked highly?) and
**context recall** (did retrieval find everything the reference answer needs?).
Alongside them is a deterministic, judge-free **retrieval hit rate** — the fraction of
questions where every expected posting made it into the context. If that drops, the
LLM-judged numbers above it are measuring a broken retriever.

Thresholds live in `THRESHOLDS` in `tests/eval/harness.py`. They are regression floors,
not targets.

**On reading the scores:** the question set in `tests/eval/fixtures/questions.json` is
41 questions — 38 grounded in specific postings, 3 deliberately unanswerable so refusal
is measured too. Sample size is what makes this gate trustworthy. At 11 questions,
repeated runs of *identical* code varied by up to 0.136 on faithfulness (0.773 to
0.909), which is wider than most regressions worth catching. At 41 the same three-run
spread is 0.015. The judge is no less noisy per question; the noise is just averaged
over more samples, and the standard error falls with the square root of n.

That is the lever to reach for. If you want tighter floors, add questions — raising the
numbers against a small sample just produces a flaky suite that everyone learns to
ignore. Floors sit ~0.05 below the lowest observed value, roughly 3x the widest observed
spread, and are tied to this judge model and this corpus: change either and re-measure.

> **Note:** ragas 0.4.x cannot be imported alongside langchain-community 0.4.x
> ([ragas#2753](https://github.com/explodinggradients/ragas/issues/2753)).
> `tests/eval/ragas_compat.py` shims the deleted module and can be deleted once
> upstream makes that import lazy.

### Code Quality

```bash
# Linting
uv run ruff check .

# Formatting
uv run ruff format .
```

## Learning Roadmap

See [AI_ENGINEER_PLAN.md](AI_ENGINEER_PLAN.md) for a comprehensive guide to mastering AI engineering through this project.

### Skills You'll Learn

- **RAG** - Semantic job matching with pgvector
- **Evaluation** - LLM-as-judge with DeepEval
- **Agent Architecture** - Production LangGraph with checkpointing
- **Prompt Engineering** - Versioned prompts with eval gates
- **Production AI** - Error handling, HITL, monitoring

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [LangChain](https://github.com/langchain-ai/langchain) - AI orchestration
- [LangGraph](https://github.com/langchain-ai/langgraph) - Agent workflows
- [FastAPI](https://github.com/tiangolo/fastapi) - Web framework
- [OpenAI](https://openai.com/) - LLM API
