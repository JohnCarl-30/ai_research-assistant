"""API-level tests for the RAG endpoints, with embeddings and the LLM stubbed."""

import pytest
from sqlalchemy import text

from app.models import Company, Job
from app.rag import qa, retriever, vector_store
from tests.test_rag_store import fake_embed


@pytest.fixture(autouse=True)
async def clean_tables(engine):
    """Truncate after each test.

    These tests must commit — the endpoint runs in its own session, so uncommitted
    data would be invisible to it. The conftest engine is session-scoped and shared,
    so without this the committed rows leak into every later test.
    """
    yield
    async with engine.begin() as conn:
        for table in ("job_chunks", "job_tags", "jobs", "companies"):
            await conn.execute(text(f"DELETE FROM {table}"))


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    def __init__(self, content: str = "Ledgerline is hiring a Senior Backend Engineer."):
        self.content = content
        self.prompts = []

    async def ainvoke(self, messages):
        self.prompts.append(messages)
        return FakeResponse(self.content)


@pytest.fixture
def fake_llm(monkeypatch):
    llm = FakeLLM()
    monkeypatch.setattr(qa, "get_answer_llm", lambda: llm)
    return llm


@pytest.fixture
def stub_embeddings(monkeypatch):
    async def embed_texts(texts: list[str]) -> list[list[float]]:
        return [fake_embed(t) for t in texts]

    async def embed_query(text: str) -> list[float]:
        return fake_embed(text)

    monkeypatch.setattr(vector_store, "embed_texts", embed_texts)
    monkeypatch.setattr(retriever, "embed_query", embed_query)


@pytest.fixture
async def seeded(session, stub_embeddings):
    company = Company(name="Ledgerline")
    session.add(company)
    await session.flush()

    job = Job(
        title="Senior Rust Engineer",
        url="https://example.com/route-rust",
        source="test",
        location="Remote",
        company_id=company.id,
        description="Build the ledger service in Rust. Payments work.",
        requirements="Rust and kubernetes",
    )
    session.add(job)
    await session.flush()
    await session.refresh(job, ["company"])
    await session.commit()
    return job


class TestIndexRoute:
    async def test_indexes_unindexed_jobs(self, client, seeded):
        response = await client.post("/api/rag/index", json={"limit": 10})

        assert response.status_code == 200
        body = response.json()
        assert body["jobs_indexed"] >= 1
        assert body["chunks_written"] >= 1

    async def test_second_run_finds_nothing_new(self, client, seeded):
        await client.post("/api/rag/index", json={"limit": 10})
        response = await client.post("/api/rag/index", json={"limit": 10})

        assert response.json()["jobs_indexed"] == 0

    async def test_reindex_all_reprocesses(self, client, seeded):
        await client.post("/api/rag/index", json={"limit": 10})
        response = await client.post("/api/rag/index", json={"limit": 10, "reindex_all": True})

        assert response.json()["jobs_indexed"] >= 1


class TestSearchRoute:
    async def test_returns_matching_chunks(self, client, seeded):
        await client.post("/api/rag/index", json={"limit": 10})

        response = await client.get("/api/rag/search", params={"q": "rust ledger", "top_k": 3})

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "rust ledger"
        assert body["results"]
        assert body["results"][0]["job_title"] == "Senior Rust Engineer"
        assert body["results"][0]["company_name"] == "Ledgerline"

    async def test_rejects_empty_query(self, client, seeded):
        assert (await client.get("/api/rag/search", params={"q": ""})).status_code == 422

    async def test_respects_top_k(self, client, seeded):
        await client.post("/api/rag/index", json={"limit": 10})
        response = await client.get("/api/rag/search", params={"q": "rust", "top_k": 1})

        assert len(response.json()["results"]) == 1


class TestAskRoute:
    async def test_answers_with_sources(self, client, seeded, fake_llm):
        await client.post("/api/rag/index", json={"limit": 10})

        response = await client.post("/api/rag/ask", json={"question": "Who needs Rust?"})

        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == fake_llm.content
        assert body["contexts"]
        assert body["sources"]

    async def test_refuses_when_nothing_is_indexed(self, client, fake_llm):
        response = await client.post("/api/rag/ask", json={"question": "Who needs Rust?"})

        assert response.status_code == 200
        assert response.json()["answer"] == qa.NO_ANSWER
        assert response.json()["contexts"] == []
        # The LLM must not be called when there is nothing to ground an answer in.
        assert fake_llm.prompts == []

    async def test_prompt_carries_the_retrieved_context(self, client, seeded, fake_llm):
        await client.post("/api/rag/index", json={"limit": 10})
        await client.post("/api/rag/ask", json={"question": "Who needs Rust?"})

        prompt = str(fake_llm.prompts[0])
        assert "Senior Rust Engineer" in prompt


class TestMatchRoute:
    async def test_ranks_jobs_by_skills(self, client, seeded):
        await client.post("/api/rag/index", json={"limit": 10})

        response = await client.post(
            "/api/rag/match",
            json={"skills": ["rust", "kubernetes"], "role": "systems engineer"},
        )

        assert response.status_code == 200
        matches = response.json()["matches"]
        assert matches
        assert matches[0]["title"] == "Senior Rust Engineer"
        assert "rust" in matches[0]["matched_skills"]

    async def test_reports_missing_skills(self, client, seeded):
        await client.post("/api/rag/index", json={"limit": 10})

        response = await client.post("/api/rag/match", json={"skills": ["rust", "cobol"]})
        matches = response.json()["matches"]

        assert "cobol" in matches[0]["missing_skills"]

    async def test_empty_skills_yields_no_matches(self, client, seeded):
        response = await client.post("/api/rag/match", json={"skills": []})
        assert response.json()["matches"] == []
