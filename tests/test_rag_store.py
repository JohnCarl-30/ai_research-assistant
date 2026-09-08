"""End-to-end index → retrieve → match against SQLite.

Embeddings are faked with a deterministic bag-of-words vector so the storage,
fusion and aggregation logic is exercised without touching the OpenAI API.
"""

import pytest

from app.models import Company, Job, JobChunk
from app.rag import matcher, retriever, vector_store

VOCAB = [
    "python",
    "rust",
    "kubernetes",
    "react",
    "ledger",
    "payments",
    "ml",
    "engineer",
    "senior",
    "remote",
]


def fake_embed(text: str) -> list[float]:
    lowered = text.lower()
    return [float(lowered.count(term)) for term in VOCAB]


@pytest.fixture
def stub_embeddings(monkeypatch):
    async def embed_texts(texts: list[str]) -> list[list[float]]:
        return [fake_embed(t) for t in texts]

    async def embed_query(text: str) -> list[float]:
        return fake_embed(text)

    monkeypatch.setattr(vector_store, "embed_texts", embed_texts)
    monkeypatch.setattr(retriever, "embed_query", embed_query)


@pytest.fixture
async def indexed_jobs(session, stub_embeddings):
    company = Company(name="Acme Payments")
    session.add(company)
    await session.flush()

    jobs = [
        Job(
            title="Senior Rust Engineer",
            url="https://example.com/rust",
            source="test",
            location="Remote",
            company_id=company.id,
            description="Build the ledger service in Rust. Payments infrastructure.",
            requirements="Rust, kubernetes",
        ),
        Job(
            title="React Frontend Engineer",
            url="https://example.com/react",
            source="test",
            location="Remote",
            company_id=company.id,
            description="Build dashboards in React.",
            requirements="React",
        ),
        Job(
            title="ML Engineer",
            url="https://example.com/ml",
            source="test",
            location="Remote",
            company_id=company.id,
            description="Train ranking models. Python and ml tooling.",
            requirements="Python, ml",
        ),
    ]
    session.add_all(jobs)
    await session.flush()

    for job in jobs:
        await session.refresh(job, ["company"])

    # Deliberately not committed: the conftest engine is session-scoped and
    # shared, so each test rolls back on close and starts from a clean table.
    written = await vector_store.index_jobs(session, jobs)
    return jobs, written


class TestIndexing:
    async def test_writes_chunks_for_every_job(self, session, indexed_jobs):
        jobs, written = indexed_jobs
        assert written > len(jobs)  # each job yields an overview plus body chunks

    async def test_chunks_carry_the_embedding_model(self, session, indexed_jobs):
        from sqlalchemy import select

        result = await session.execute(select(JobChunk).limit(1))
        chunk = result.scalar_one()
        assert chunk.embedding_model
        assert chunk.embedding is not None

    async def test_reindexing_replaces_rather_than_duplicates(self, session, indexed_jobs):
        from sqlalchemy import func, select

        jobs, _ = indexed_jobs
        before = (await session.execute(select(func.count(JobChunk.id)))).scalar()

        await vector_store.index_jobs(session, jobs)

        after = (await session.execute(select(func.count(JobChunk.id)))).scalar()
        assert after == before

    async def test_unindexed_jobs_is_empty_once_indexed(self, session, indexed_jobs):
        assert await vector_store.unindexed_jobs(session) == []

    async def test_indexing_nothing_is_a_noop(self, session, stub_embeddings):
        assert await vector_store.index_jobs(session, []) == 0


class TestSearch:
    async def test_finds_the_semantically_closest_job(self, session, indexed_jobs):
        results = await vector_store.search(session, fake_embed("rust ledger payments"), limit=5)

        assert results
        assert "Rust" in results[0].job_title

    async def test_results_are_ordered_by_score(self, session, indexed_jobs):
        results = await vector_store.search(session, fake_embed("react"), limit=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_hydrates_job_and_company(self, session, indexed_jobs):
        results = await vector_store.search(session, fake_embed("react"), limit=1)
        assert results[0].company_name == "Acme Payments"
        assert results[0].job_url.startswith("https://example.com/")

    async def test_empty_query_vector_returns_nothing(self, session, indexed_jobs):
        assert await vector_store.search(session, [], limit=5) == []

    async def test_respects_limit(self, session, indexed_jobs):
        assert len(await vector_store.search(session, fake_embed("engineer"), limit=2)) == 2


class TestHybridRetrieve:
    async def test_retrieves_relevant_chunks(self, session, indexed_jobs):
        results = await retriever.retrieve(session, "rust ledger", top_k=3)

        assert results
        assert any("Rust" in r.chunk.job_title for r in results)

    async def test_keyword_only_term_is_found_by_the_sparse_arm(self, session, indexed_jobs):
        results = await retriever.retrieve(session, "dashboards", top_k=5)

        # "dashboards" is not in the fake embedding vocabulary, so a hit here can
        # only have come from BM25 — this is the arm hybrid retrieval buys us.
        assert any(r.sparse_rank is not None for r in results)
        assert any("React" in r.chunk.job_title for r in results)

    async def test_dense_only_mode_skips_bm25(self, session, indexed_jobs):
        results = await retriever.retrieve(session, "rust", top_k=3, hybrid=False)
        assert all(r.sparse_rank is None for r in results)

    async def test_respects_top_k(self, session, indexed_jobs):
        assert len(await retriever.retrieve(session, "engineer", top_k=2)) == 2


class TestMatcher:
    async def test_ranks_jobs_against_skills(self, session, indexed_jobs):
        matches = await matcher.match_jobs(session, ["rust", "kubernetes"], limit=3)

        assert matches
        assert "Rust" in matches[0].title

    async def test_reports_matched_and_missing_skills(self, session, indexed_jobs):
        matches = await matcher.match_jobs(session, ["rust", "cobol"], limit=3)
        rust_job = next(m for m in matches if "Rust" in m.title)

        assert "rust" in rust_job.matched_skills
        assert "cobol" in rust_job.missing_skills

    async def test_deduplicates_chunks_into_one_job(self, session, indexed_jobs):
        matches = await matcher.match_jobs(session, ["rust", "payments", "ledger"], limit=10)
        job_ids = [m.job_id for m in matches]

        assert len(job_ids) == len(set(job_ids))

    async def test_no_skills_returns_nothing(self, session, indexed_jobs):
        assert await matcher.match_jobs(session, []) == []

    async def test_attaches_evidence(self, session, indexed_jobs):
        matches = await matcher.match_jobs(session, ["rust"], limit=1)
        assert matches[0].evidence
