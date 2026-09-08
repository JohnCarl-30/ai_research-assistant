"""Ragas quality gate for the RAG pipeline.

Skipped unless RUN_EVAL=1. These tests make real OpenAI calls (embeddings, one
answer per question, several judge calls per metric), so they are opt-in rather
than part of the default suite:

    RUN_EVAL=1 uv run pytest tests/eval -v
"""

import os

import pytest

from app.rag.qa import NO_ANSWER
from tests.eval.harness import THRESHOLDS, evaluate_rag

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        os.getenv("RUN_EVAL") != "1",
        reason="Costs OpenAI calls. Set RUN_EVAL=1 to run.",
    ),
]


@pytest.fixture(scope="module")
async def report():
    """One evaluation run shared by every assertion below."""
    return await evaluate_rag()


async def test_corpus_was_indexed(report):
    assert report["chunks_indexed"] > 0


async def test_retrieval_finds_the_expected_postings(report):
    hit_rate = report["retrieval_hit_rate"]
    assert hit_rate is not None
    # Read 100% on all three calibration runs over 38 grounded questions, so
    # 0.95 leaves room for a single case to drift without failing the suite.
    assert hit_rate >= 0.95, f"retrieval hit rate {hit_rate:.2f} — the retriever is missing jobs"


async def test_every_metric_was_scored(report):
    missing = set(THRESHOLDS) - set(report["scores"])
    assert not missing, f"ragas returned no score for: {sorted(missing)}"


@pytest.mark.parametrize("metric", sorted(THRESHOLDS))
async def test_metric_meets_threshold(report, metric):
    score = report["scores"].get(metric)
    assert score is not None, f"{metric} was not scored"
    assert score >= THRESHOLDS[metric], (
        f"{metric} = {score:.3f}, below floor {THRESHOLDS[metric]:.2f}"
    )


async def test_out_of_scope_questions_are_refused(report):
    """Every question the corpus cannot answer must be refused, not invented.

    Checked across all of them, not just the first. This previously pulled a
    single case with `next(...)` and matched on the word "japan", so adding
    out-of-scope cases silently left them untested — the assertion could only
    ever fail for the one question it was written against.
    """
    cases = [c for c in report["cases"] if not c.expected_job_urls]
    assert cases, "the question set has no out-of-scope case to check refusal with"

    answered = [c.question for c in cases if NO_ANSWER.lower() not in c.answer.lower()]
    assert not answered, f"out-of-scope questions were answered instead of refused: {answered}"
