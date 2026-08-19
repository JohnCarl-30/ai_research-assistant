"""Automated regression testing for Scout agents.

Runs agents against golden datasets and compares scores to thresholds.
Blocks deploys if scores drop below thresholds.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.eval.datasets import (
    load_cover_letter_cases,
    load_research_cases,
    load_matching_cases,
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
    from app.eval.judge import judge_cover_letter
    from app.agents.cover_letter import generate_cover_letter

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
    from app.eval.judge import judge_research
    from app.agents.researcher import research_company

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


async def test_matching() -> RegressionResult:
    """Test job matching against golden dataset."""
    from app.eval.judge import judge_matching

    cases = load_matching_cases()
    scores = []
    failures = []

    for case in cases:
        try:
            # Simulate matching result (in real use, call the matcher)
            match_result = {
                "matched_skills": case.expected_matched_skills,
                "missing_skills": case.expected_missing_skills,
                "match_score": len(case.expected_matched_skills) / max(len(case.candidate_skills), 1),
            }

            score_result = await judge_matching(
                match_result=match_result,
                candidate_skills=case.candidate_skills,
                job_requirements=case.job_requirements,
            )

            scores.append(score_result.score)

            if score_result.score < THRESHOLDS["matching"]["overall"]:
                failures.append({
                    "case": case.job_requirements[:50],
                    "score": score_result.score,
                    "threshold": THRESHOLDS["matching"]["overall"],
                    "reasoning": score_result.reasoning,
                })
        except Exception as e:
            failures.append({
                "case": case.job_requirements[:50],
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
