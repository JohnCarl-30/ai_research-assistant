"""Evaluation harness for Scout agents.

Provides:
- LLM-as-judge scoring
- Golden dataset management
- Regression testing
- CI/CD eval gates
"""

from app.eval.judge import (
    ScoreResult,
    judge_cover_letter,
    judge_research,
    judge_matching,
)
from app.eval.datasets import (
    load_cover_letter_cases,
    load_research_cases,
    load_matching_cases,
)
from app.eval.regression import (
    run_regression_test,
    RegressionResult,
)

__all__ = [
    "ScoreResult",
    "judge_cover_letter",
    "judge_research",
    "judge_matching",
    "load_cover_letter_cases",
    "load_research_cases",
    "load_matching_cases",
    "run_regression_test",
    "RegressionResult",
]
