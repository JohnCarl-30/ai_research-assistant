"""Golden datasets for agent evaluation.

These are the "expected" outputs that agents should produce.
Used for regression testing and quality gates.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass
class CoverLetterCase:
    """Golden test case for cover letter generation."""
    job_title: str
    company_name: str
    job_description: str
    user_skills: list[str]
    expected_keywords: list[str]  # Must include these
    min_paragraphs: int = 3
    max_paragraphs: int = 5


@dataclass
class ResearchCase:
    """Golden test case for company research."""
    company_name: str
    expected_fields: list[str]  # Must have these fields
    min_completeness: float = 0.8  # At least 80% of fields


@dataclass
class MatchingCase:
    """Golden test case for job-candidate matching."""
    candidate_skills: list[str]
    job_requirements: str
    expected_match_range: tuple[float, float] = (0.3, 0.9)
    expected_matched_skills: list[str] = field(default_factory=list)
    expected_missing_skills: list[str] = field(default_factory=list)


def load_cover_letter_cases() -> list[CoverLetterCase]:
    """Load golden test cases for cover letter generation."""
    return [
        CoverLetterCase(
            job_title="Senior Python Developer",
            company_name="TechCorp",
            job_description="We need a senior Python developer with FastAPI and React experience.",
            user_skills=["Python", "FastAPI", "React", "PostgreSQL"],
            expected_keywords=["Python", "FastAPI", "experience"],
            min_paragraphs=3,
        ),
        CoverLetterCase(
            job_title="Full Stack Engineer",
            company_name="StartupXYZ",
            job_description="Looking for a full stack engineer with TypeScript and Node.js.",
            user_skills=["TypeScript", "Node.js", "React", "AWS"],
            expected_keywords=["TypeScript", "full stack"],
            min_paragraphs=3,
        ),
        CoverLetterCase(
            job_title="ML Engineer",
            company_name="AI Labs",
            job_description="ML engineer needed with PyTorch and LangChain experience.",
            user_skills=["Python", "PyTorch", "LangChain", "OpenAI"],
            expected_keywords=["machine learning", "PyTorch"],
            min_paragraphs=3,
        ),
    ]


def load_research_cases() -> list[ResearchCase]:
    """Load golden test cases for company research."""
    return [
        ResearchCase(
            company_name="Google",
            expected_fields=["mission", "tech_stack", "size", "summary"],
            min_completeness=0.9,
        ),
        ResearchCase(
            company_name="Microsoft",
            expected_fields=["mission", "tech_stack", "size", "summary"],
            min_completeness=0.9,
        ),
        ResearchCase(
            company_name="Stripe",
            expected_fields=["mission", "tech_stack", "size", "summary"],
            min_completeness=0.8,
        ),
    ]


def load_matching_cases() -> list[MatchingCase]:
    """Load golden test cases for job-candidate matching."""
    return [
        MatchingCase(
            candidate_skills=["Python", "FastAPI", "React", "PostgreSQL"],
            job_requirements="Senior Python developer with FastAPI and React experience",
            expected_match_range=(0.7, 0.95),
            expected_matched_skills=["Python", "FastAPI", "React"],
        ),
        MatchingCase(
            candidate_skills=["Python", "Django", "jQuery"],
            job_requirements="Full stack engineer with React and Node.js",
            expected_match_range=(0.2, 0.5),
            expected_missing_skills=["React", "Node.js"],
        ),
        MatchingCase(
            candidate_skills=["Python", "PyTorch", "LangChain"],
            job_requirements="ML engineer with TensorFlow and production ML experience",
            expected_match_range=(0.3, 0.6),
            expected_matched_skills=["Python"],
            expected_missing_skills=["TensorFlow"],
        ),
    ]


def save_eval_results(results: dict, filename: str = "eval_results.json"):
    """Save evaluation results to file."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    filepath = FIXTURES_DIR / filename
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2, default=str)


def load_eval_results(filename: str = "eval_results.json") -> dict | None:
    """Load evaluation results from file."""
    filepath = FIXTURES_DIR / filename
    if not filepath.exists():
        return None
    with open(filepath) as f:
        return json.load(f)
