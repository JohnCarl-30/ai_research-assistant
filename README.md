# AI Research Assistant

An AI-powered job search assistant that monitors job boards, researches companies, and generates personalized cover letters using LangChain, LangGraph, and OpenAI.

## Features

- **Job Board Monitoring** - Scrape LinkedIn and Indeed for job opportunities
- **Company Research** - AI-powered analysis of company mission, tech stack, and culture
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
│   │   ├── embeddings.py      # Embedding generation
│   │   ├── vector_store.py    # pgvector operations
│   │   ├── retriever.py       # Hybrid search
│   │   └── matcher.py         # Job-candidate matching
│   ├── prompts/
│   │   ├── cover_letter.py    # Versioned prompts
│   │   ├── research.py
│   │   └── matching.py
│   ├── api/
│   │   └── routes.py          # API endpoints
│   ├── config.py              # Settings
│   ├── database.py            # PostgreSQL
│   └── main.py                # FastAPI app
├── tests/
│   ├── eval/
│   │   ├── judge.py           # LLM-as-judge
│   │   └── fixtures/          # Test data
│   └── ...
├── docker-compose.yml         # PostgreSQL
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

### Example Usage

```bash
# Full pipeline: scrape jobs + research companies + generate cover letters
curl "http://localhost:8000/scan?query=python+developer&location=remote&skills=Python,FastAPI,React,LangChain"

# Generate a single cover letter
curl "http://localhost:8000/cover-letter?job_title=Python+Developer&company_name=Google&skills=Python,FastAPI,React"
```

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
```

## Development

### Running Tests

```bash
# Unit tests
uv run pytest

# With coverage
uv run pytest --cov=app

# Evaluation tests
uv run python scripts/eval.py
```

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
