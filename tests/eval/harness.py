"""Run Scout's RAG pipeline over a fixed corpus and score it with ragas.

The corpus lives in an isolated in-memory SQLite database, so evaluation needs
no Postgres — `app.rag.vector_store.search` falls back to Python-side cosine on
non-Postgres dialects. It does make real OpenAI calls: embeddings to index and
query, one answer per question, and several judge calls per metric.

The ragas imports below only work because importing this module first executes
`tests/eval/__init__.py`, which installs the langchain-community shim. Do not
move that shim into this file — an import sorter will hoist the ragas imports
above it and the workaround silently stops applying.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import EvaluationDataset, aevaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper

# Deliberately the legacy metrics, despite the DeprecationWarning pointing at
# `ragas.metrics.collections`. On ragas 0.4.3 the collections metrics are not
# wired into the evaluation orchestration: `aevaluate` type-checks its metrics
# against the legacy `Metric` base and rejects them with
#
#     TypeError: All metrics must be initialised metric objects
#
# while the collections classes only expose `ascore`/`abatch_score`. Switching
# the imports therefore breaks the harness in one of two ways — a ValueError at
# construction if the Langchain wrappers are kept, or the TypeError above once
# they are swapped for llm_factory/embedding_factory. Completing that migration
# means hand-rolling the per-sample scoring loop *and* re-calibrating the floors
# below, since they were measured against these implementations. Do that as its
# own change, not as an import tidy-up.
from ragas.metrics import (
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
    ResponseRelevancy,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base
from app.models import Company, Job
from app.rag.qa import answer_job_question
from app.rag.vector_store import index_jobs

FIXTURES = Path(__file__).parent / "fixtures"

# Floors, not targets — they exist to catch regressions, not to certify quality.
#
# Observed across runs on 2026-08-06 (gpt-4o-mini judge, text-embedding-3-small,
# top_k=5), same code, same corpus:
#   faithfulness      0.773 - 0.909
#   answer_relevancy  0.687 - 0.775
#   context_precision 0.806 - 0.818
#   context_recall    0.909 - 1.000
#
# That spread is the point: an LLM judge over 11 questions swings ~0.15 run to
# run even at temperature 0, because the metrics re-decompose answers into
# statements each time. Floors are set ~0.10 below the *lowest* observed value,
# not below the best one — a floor calibrated on a good run fails on the next
# good run, and a flaky gate gets ignored. Tightening these means adding
# questions to shrink the standard error, not just raising the numbers.
THRESHOLDS = {
    "faithfulness": 0.65,
    "answer_relevancy": 0.60,
    "llm_context_precision_with_reference": 0.70,
    "context_recall": 0.75,
}


@dataclass
class EvalCase:
    question: str
    reference: str
    expected_job_urls: list[str] = field(default_factory=list)
    answer: str = ""
    contexts: list[str] = field(default_factory=list)
    retrieved_job_urls: list[str] = field(default_factory=list)


def load_jobs() -> list[dict]:
    return json.loads((FIXTURES / "jobs.json").read_text())


def load_cases() -> list[EvalCase]:
    raw = json.loads((FIXTURES / "questions.json").read_text())
    return [EvalCase(**item) for item in raw]


async def build_corpus(session: AsyncSession) -> int:
    """Insert and index the fixture postings. Returns the chunk count."""
    companies: dict[str, Company] = {}
    jobs: list[Job] = []

    for record in load_jobs():
        name = record["company"]
        if name not in companies:
            company = Company(name=name)
            session.add(company)
            companies[name] = company
    await session.flush()

    for record in load_jobs():
        jobs.append(
            Job(
                title=record["title"],
                url=record["url"],
                source=record["source"],
                location=record.get("location"),
                salary_range=record.get("salary_range"),
                description=record.get("description"),
                requirements=record.get("requirements"),
                company_id=companies[record["company"]].id,
            )
        )
    session.add_all(jobs)
    await session.flush()

    for job in jobs:
        await session.refresh(job, ["company"])

    return await index_jobs(session, jobs)


async def run_pipeline(session: AsyncSession, cases: list[EvalCase], top_k: int) -> list[EvalCase]:
    """Answer every question, recording the contexts each answer was built from."""
    for case in cases:
        result = await answer_job_question(session, case.question, top_k=top_k)
        case.answer = result.answer
        case.contexts = result.contexts
        case.retrieved_job_urls = list(dict.fromkeys(r.chunk.job_url for r in result.retrieved))
    return cases


def build_dataset(cases: list[EvalCase]) -> EvaluationDataset:
    return EvaluationDataset.from_list(
        [
            {
                "user_input": case.question,
                "retrieved_contexts": case.contexts,
                "response": case.answer,
                "reference": case.reference,
            }
            for case in cases
        ]
    )


def build_metrics():
    settings = get_settings()
    judge = LangchainLLMWrapper(
        ChatOpenAI(
            model=settings.eval_llm_model,
            temperature=0,
            api_key=settings.openai_api_key,
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
        )
    )
    return judge, [
        Faithfulness(llm=judge),
        ResponseRelevancy(llm=judge, embeddings=embeddings),
        LLMContextPrecisionWithReference(llm=judge),
        LLMContextRecall(llm=judge),
    ]


def aggregate_scores(result) -> dict[str, float]:
    """Mean of each metric across samples, skipping the ones ragas returned NaN for.

    A metric can be NaN for a single sample (a judge parse failure, or a case the
    metric does not apply to), and one NaN must not poison the whole average.
    """
    per_metric: dict[str, list[float]] = {}
    for sample in result.scores:
        for name, value in sample.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if math.isnan(value):
                continue
            per_metric.setdefault(name, []).append(float(value))

    return {name: sum(values) / len(values) for name, values in per_metric.items() if values}


def retrieval_hit_rate(cases: list[EvalCase]) -> float | None:
    """Fraction of cases where every expected posting was retrieved.

    A deterministic, judge-free check on retrieval alone — if this drops, the
    LLM-scored metrics below it are measuring a broken retriever.

    Deliberately lenient: it checks that the right *posting* was reached, not
    that the answer-bearing passage was. It read 100% on a run where a question
    was still refused because only the posting's header chunk was retrieved.
    Read it alongside context_recall, which does judge passage content.
    """
    grounded = [c for c in cases if c.expected_job_urls]
    if not grounded:
        return None
    hits = sum(set(c.expected_job_urls).issubset(set(c.retrieved_job_urls)) for c in grounded)
    return hits / len(grounded)


async def evaluate_rag(top_k: int | None = None) -> dict:
    """Build the corpus, answer every question, and score with ragas."""
    settings = get_settings()
    top_k = top_k or settings.rag_top_k

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            chunks = await build_corpus(session)
            cases = await run_pipeline(session, load_cases(), top_k)
    finally:
        await engine.dispose()

    # aevaluate, not evaluate: the sync entry point applies nest_asyncio to
    # re-enter the running loop, which breaks the async OpenAI client under
    # Python 3.14 (every judge call fails with APIConnectionError) and then
    # crashes on loop shutdown. The native coroutine never patches the loop.
    judge, metrics = build_metrics()
    result = await aevaluate(
        dataset=build_dataset(cases),
        metrics=metrics,
        llm=judge,
        show_progress=False,
    )

    return {
        "chunks_indexed": chunks,
        "top_k": top_k,
        "cases": cases,
        "scores": aggregate_scores(result),
        "retrieval_hit_rate": retrieval_hit_rate(cases),
        "result": result,
    }
