"""End-to-end tests for the evaluation system."""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestEvalDatasets:
    """Test golden dataset loading."""

    def test_load_cover_letter_cases(self):
        """Test loading cover letter golden dataset."""
        from app.eval.datasets import load_cover_letter_cases

        cases = load_cover_letter_cases()
        assert len(cases) == 3
        assert cases[0].job_title == "Senior Python Developer"
        assert cases[0].company_name == "TechCorp"
        assert "Python" in cases[0].user_skills
        assert cases[0].min_paragraphs == 3

    def test_load_research_cases(self):
        """Test loading research golden dataset."""
        from app.eval.datasets import load_research_cases

        cases = load_research_cases()
        assert len(cases) == 3
        assert cases[0].company_name == "Google"
        assert "mission" in cases[0].expected_fields
        assert cases[0].min_completeness == 0.9

    def test_load_matching_cases(self):
        """Test loading matching golden dataset."""
        from app.eval.datasets import load_matching_cases

        cases = load_matching_cases()
        assert len(cases) == 3
        assert "Python" in cases[0].candidate_skills
        assert cases[0].expected_match_range == (0.7, 0.95)

        # Every case must carry a postable job, because the regression test
        # indexes it and runs the real matcher over it.
        for case in cases:
            assert case.job_title
            assert case.job_description
            assert case.job_requirements

        # matched/missing partition the candidate's own skills — see MatchingCase.
        for case in cases:
            expected = {s.lower() for s in case.expected_matched_skills}
            expected |= {s.lower() for s in case.expected_missing_skills}
            assert expected == {s.lower() for s in case.candidate_skills}, (
                f"{case.job_title}: expected matched+missing must partition candidate_skills"
            )


class TestEvalJudge:
    """Test LLM-as-judge scoring."""

    @pytest.mark.asyncio
    async def test_judge_cover_letter_structure(self):
        """Test cover letter judge returns correct structure."""
        from app.eval.judge import ScoreResult

        result = ScoreResult(
            score=0.85,
            reasoning="Good cover letter",
            details={"relevance": 0.9, "skills_match": 0.8},
        )

        assert result.score == 0.85
        assert result.reasoning == "Good cover letter"
        assert result.details["relevance"] == 0.9
        assert result.details["skills_match"] == 0.8

    @pytest.mark.asyncio
    async def test_judge_research_structure(self):
        """Test research judge returns correct structure."""
        from app.eval.judge import ScoreResult

        result = ScoreResult(
            score=0.9,
            reasoning="Comprehensive research",
            details={"completeness": 0.95, "accuracy": 0.85},
        )

        assert result.score == 0.9
        assert result.details["completeness"] == 0.95

    @pytest.mark.asyncio
    async def test_judge_matching_structure(self):
        """Test matching judge returns correct structure."""
        from app.eval.judge import ScoreResult

        result = ScoreResult(
            score=0.8,
            reasoning="Good matching",
            details={"skill_identification": 0.85, "recommendation": 0.8},
        )

        assert result.score == 0.8
        assert result.details["skill_identification"] == 0.85


class TestEvalRegression:
    """Test regression testing."""

    def test_thresholds_configured(self):
        """Test that all thresholds are properly configured."""
        from app.eval.regression import THRESHOLDS

        assert "cover_letter" in THRESHOLDS
        assert "research" in THRESHOLDS
        assert "matching" in THRESHOLDS

        assert THRESHOLDS["cover_letter"]["overall"] == 0.7

        # RAG floors are not mirrored here — tests/eval/harness.py owns them.
        assert "rag" not in THRESHOLDS, (
            "RAG floors belong to the harness that calibrated them; a copy here "
            "drifts out of sync with the metric names ragas actually emits"
        )

    def test_regression_result_structure(self):
        """Test RegressionResult dataclass structure."""
        from app.eval.regression import RegressionResult

        result = RegressionResult(
            passed=True,
            agent="cover_letter",
            scores={"overall": 0.85},
            thresholds={"overall": 0.7},
            failures=[],
        )

        assert result.passed is True
        assert result.agent == "cover_letter"
        assert result.scores["overall"] == 0.85
        assert len(result.failures) == 0

    def test_check_eval_gate_pass(self):
        """Test eval gate passes when all tests pass."""
        from app.eval.regression import RegressionResult, check_eval_gate

        results = [
            RegressionResult(passed=True, agent="cover_letter", scores={}, thresholds={}),
            RegressionResult(passed=True, agent="research", scores={}, thresholds={}),
        ]

        assert check_eval_gate(results) is True

    def test_check_eval_gate_fail(self):
        """Test eval gate fails when any test fails."""
        from app.eval.regression import RegressionResult, check_eval_gate

        results = [
            RegressionResult(passed=True, agent="cover_letter", scores={}, thresholds={}),
            RegressionResult(passed=False, agent="research", scores={}, thresholds={}),
        ]

        assert check_eval_gate(results) is False


class TestEvalIntegration:
    """Integration tests combining multiple eval components."""

    def test_full_dataset_loading(self):
        """Test loading all golden datasets."""
        from app.eval.datasets import (
            load_cover_letter_cases,
            load_research_cases,
            load_matching_cases,
        )

        cover_cases = load_cover_letter_cases()
        research_cases = load_research_cases()
        matching_cases = load_matching_cases()

        assert len(cover_cases) == 3
        assert len(research_cases) == 3
        assert len(matching_cases) == 3

        # Verify structure
        for case in cover_cases:
            assert hasattr(case, "job_title")
            assert hasattr(case, "company_name")
            assert hasattr(case, "expected_keywords")

        for case in research_cases:
            assert hasattr(case, "company_name")
            assert hasattr(case, "expected_fields")

        for case in matching_cases:
            assert hasattr(case, "candidate_skills")
            assert hasattr(case, "job_requirements")

    def test_eval_exports(self):
        """Test all eval exports are available."""
        from app.eval import (
            ScoreResult,
            judge_cover_letter,
            judge_research,
            judge_matching,
            load_cover_letter_cases,
            load_research_cases,
            load_matching_cases,
            run_regression_test,
            RegressionResult,
        )

        assert ScoreResult is not None
        assert judge_cover_letter is not None
        assert judge_research is not None
        assert judge_matching is not None
        assert load_cover_letter_cases is not None
        assert load_research_cases is not None
        assert load_matching_cases is not None
        assert run_regression_test is not None
        assert RegressionResult is not None

    def test_thresholds_cover_all_agents(self):
        """Test thresholds are defined for all agents."""
        from app.eval.regression import THRESHOLDS

        required_agents = ["cover_letter", "research", "matching"]
        for agent in required_agents:
            assert agent in THRESHOLDS, f"Missing thresholds for {agent}"
            assert len(THRESHOLDS[agent]) > 0, f"Empty thresholds for {agent}"
