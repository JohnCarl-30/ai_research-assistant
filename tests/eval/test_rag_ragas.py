"""Ragas quality gate for the RAG pipeline.

Skipped unless RUN_EVAL=1. These tests make real OpenAI calls (embeddings, one
answer per question, several judge calls per metric), so they are opt-in rather
than part of the default suite:

    RUN_EVAL=1 uv run pytest tests/eval -v
"""

import os

import pytest

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
    assert hit_rate >= 0.8, f"retrieval hit rate {hit_rate:.2f} — the retriever is missing jobs"


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


async def test_out_of_scope_question_is_refused(report):
    """The corpus says nothing about Japan; the answer must not invent one."""
    case = next(c for c in report["cases"] if not c.expected_job_urls)
    lowered = case.answer.lower()
    assert "japan" not in lowered or "don't have enough information" in lowered
