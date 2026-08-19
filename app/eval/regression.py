"""Automated regression testing for Scout agents.

Runs agents against golden datasets and compares scores to thresholds.
Blocks deploys if scores drop below thresholds.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.eval.datasets import (
    load_cover_letter_cases,
    load_matching_cases,
    load_research_cases,
    save_eval_results,
)


@dataclass
class RegressionResult:
    """Result from regression test."""
    passed: bool
    agent: str
    scores: dict[str, float]
    thresholds: dict[str, float]
    failures: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# Regression thresholds - scores below these FAIL the gate
THRESHOLDS = {
    "cover_letter": {
        "overall": 0.7,
        "relevance": 0.6,
        "skills_match": 0.6,
        "tone": 0.7,
    },
    "research": {
        "overall": 0.7,
        "completeness": 0.8,
        "accuracy": 0.6,
    },
    "matching": {
        "overall": 0.6,
        "skill_identification": 0.7,
        "recommendation": 0.6,
    },
}

# RAG floors deliberately live elsewhere: tests/eval/harness.py owns them,
# alongside the observed run-to-run spread they were calibrated against. A
# second copy here drifted once already — it keyed context precision as
# "context_precision" while ragas emits "llm_context_precision_with_reference",
# so that floor silently matched nothing and was never enforced.


async def test_cover_letters() -> RegressionResult:
    """Test cover letter generation against golden dataset."""
    from app.agents.cover_letter import generate_cover_letter
    from app.eval.judge import judge_cover_letter

    cases = load_cover_letter_cases()
    scores = []
    failures = []

    for case in cases:
        try:
            result = await generate_cover_letter(
                job_title=case.job_title,
                company_name=case.company_name,
                job_description=case.job_description,
                user_skills=case.user_skills,
            )

            score_result = await judge_cover_letter(
                cover_letter=result["cover_letter"],
                job_title=case.job_title,
                company_name=case.company_name,
                job_description=case.job_description,
                user_skills=case.user_skills,
            )

            scores.append(score_result.score)

            # Check thresholds
            if score_result.score < THRESHOLDS["cover_letter"]["overall"]:
                failures.append({
                    "case": f"{case.job_title} at {case.company_name}",
                    "score": score_result.score,
                    "threshold": THRESHOLDS["cover_letter"]["overall"],
                    "reasoning": score_result.reasoning,
                })
        except Exception as e:
            failures.append({
                "case": f"{case.job_title} at {case.company_name}",
                "error": str(e),
            })

    avg_score = sum(scores) / len(scores) if scores else 0

    return RegressionResult(
        passed=len(failures) == 0 and avg_score >= THRESHOLDS["cover_letter"]["overall"],
        agent="cover_letter",
        scores={"overall": avg_score},
        thresholds=THRESHOLDS["cover_letter"],
        failures=failures,
    )


async def test_research() -> RegressionResult:
    """Test company research against golden dataset."""
    from app.agents.researcher import research_company
    from app.eval.judge import judge_research

    cases = load_research_cases()
    scores = []
    failures = []

    for case in cases:
        try:
            result = await research_company(case.company_name)

            score_result = await judge_research(
                research_result=result,
                company_name=case.company_name,
            )

            scores.append(score_result.score)

            if score_result.score < THRESHOLDS["research"]["overall"]:
                failures.append({
                    "case": case.company_name,
                    "score": score_result.score,
                    "threshold": THRESHOLDS["research"]["overall"],
                    "reasoning": score_result.reasoning,
                })
        except Exception as e:
            failures.append({
                "case": case.company_name,
                "error": str(e),
            })

    avg_score = sum(scores) / len(scores) if scores else 0

    return RegressionResult(
        passed=len(failures) == 0 and avg_score >= THRESHOLDS["research"]["overall"],
        agent="research",
        scores={"overall": avg_score},
        thresholds=THRESHOLDS["research"],
        failures=failures,
    )


@asynccontextmanager
async def _matching_corpus(cases: list) -> AsyncIterator[tuple[Any, list[str]]]:
    """Index each case's posting in a throwaway SQLite database.

    Mirrors the RAG harness: `app.rag.vector_store.search` falls back to
    Python-side cosine on non-Postgres dialects, so the matcher runs end to end
    with no Postgres. All the postings share one corpus on purpose — with a
    single document, ranking is vacuous and the matcher's retrieval arm is not
    exercised at all.

    Yields the session and, positionally per case, the URL of that case's job.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.database import Base
    from app.models import Company, Job
    from app.rag.vector_store import index_jobs

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            company = Company(name="Eval Corp")
            session.add(company)
            await session.flush()

            jobs = [
                Job(
                    title=case.job_title,
                    url=f"https://example.com/eval/matching-{i}",
                    source="eval",
                    description=case.job_description,
                    requirements=case.job_requirements,
                    company_id=company.id,
                )
                for i, case in enumerate(cases)
            ]
            session.add_all(jobs)
            await session.flush()
            for job in jobs:
                await session.refresh(job, ["company"])

            await index_jobs(session, jobs)
            yield session, [job.url for job in jobs]
    finally:
        await engine.dispose()


async def test_matching() -> RegressionResult:
    """Test job matching against golden dataset.

    Runs the real matcher over a real index. The deterministic checks below are
    the substance of this gate — which skills a posting evidences is a fact, not
    a judgement — and the LLM judge scores the result on top of them.
    """
    from app.eval.judge import judge_matching
    from app.rag.matcher import match_jobs

    cases = load_matching_cases()
    scores = []
    failures = []

    async with _matching_corpus(cases) as (session, urls):
        for case, url in zip(cases, urls):
            label = case.job_requirements[:50]
            try:
                ranked = await match_jobs(session, case.candidate_skills, limit=len(cases))
                match = next((m for m in ranked if m.url == url), None)
                if match is None:
                    failures.append({
                        "case": label,
                        "error": "matcher did not retrieve this posting at all",
                    })
                    continue

                matched = {s.lower() for s in match.matched_skills}
                missing = {s.lower() for s in match.missing_skills}
                coverage = len(matched) / max(len(case.candidate_skills), 1)

                # Deterministic checks, judge-free.
                expected_matched = {s.lower() for s in case.expected_matched_skills}
                expected_missing = {s.lower() for s in case.expected_missing_skills}
                low, high = case.expected_match_range

                if matched != expected_matched:
                    failures.append({
                        "case": label,
                        "error": "matched_skills mismatch",
                        "expected": sorted(expected_matched),
                        "actual": sorted(matched),
                    })
                if missing != expected_missing:
                    failures.append({
                        "case": label,
                        "error": "missing_skills mismatch",
                        "expected": sorted(expected_missing),
                        "actual": sorted(missing),
                    })
                if not low <= coverage <= high:
                    failures.append({
                        "case": label,
                        "error": "match_score outside expected range",
                        "expected": [low, high],
                        "actual": round(coverage, 3),
                    })

                match_result = {
                    "matched_skills": sorted(match.matched_skills),
                    "missing_skills": sorted(match.missing_skills),
                    "match_score": round(coverage, 3),
                    "rank": ranked.index(match) + 1,
                    "of_postings": len(ranked),
                }
                posting = f"{case.job_title}\n{case.job_description}\n{case.job_requirements}"

                score_result = await judge_matching(
                    match_result=match_result,
                    candidate_skills=case.candidate_skills,
                    job_requirements=posting,
                )

                scores.append(score_result.score)

                if score_result.score < THRESHOLDS["matching"]["overall"]:
                    failures.append({
                        "case": label,
                        "score": score_result.score,
                        "threshold": THRESHOLDS["matching"]["overall"],
                        "reasoning": score_result.reasoning,
                    })
            except Exception as e:
                failures.append({
                    "case": label,
                    "error": str(e),
                })

    avg_score = sum(scores) / len(scores) if scores else 0

    return RegressionResult(
        passed=len(failures) == 0 and avg_score >= THRESHOLDS["matching"]["overall"],
        agent="matching",
        scores={"overall": avg_score},
        thresholds=THRESHOLDS["matching"],
        failures=failures,
    )


async def run_regression_test(agent: str | None = None) -> list[RegressionResult]:
    """Run regression tests for specified agent(s)."""
    results = []

    if agent is None or agent == "cover_letter":
        results.append(await test_cover_letters())

    if agent is None or agent == "research":
        results.append(await test_research())

    if agent is None or agent == "matching":
        results.append(await test_matching())

    # Save results
    save_eval_results({
        "timestamp": datetime.now().isoformat(),
        "results": [
            {
                "agent": r.agent,
                "passed": r.passed,
                "scores": r.scores,
                "failures": r.failures,
            }
            for r in results
        ],
    })

    return results


def check_eval_gate(results: list[RegressionResult]) -> bool:
    """Check if all evaluations passed. Used to block deploys."""
    return all(r.passed for r in results)
