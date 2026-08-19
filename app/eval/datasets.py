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
    """Golden test case for job-candidate matching.

    The posting fields are real input, not decoration: the case is evaluated by
    indexing this posting and running `app.rag.matcher.match_jobs` against it,
    so the matcher has to retrieve it and read its own evidence out of it.

    Note the direction of `expected_matched_skills` / `expected_missing_skills`.
    They partition `candidate_skills` by whether the *posting* evidences them —
    which is what the matcher reports. They are not the job's requirements that
    the candidate lacks; an earlier version of this dataset assumed the latter,
    and nothing caught it because the matcher was never actually called.
    """
    candidate_skills: list[str]
    job_title: str
    job_description: str
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
        # Strong fit: three of four skills are evidenced in the posting.
        MatchingCase(
            candidate_skills=["Python", "FastAPI", "React", "PostgreSQL"],
            job_title="Senior Python Developer",
            job_description=(
                "We are building a customer-facing analytics product. The team ships "
                "a FastAPI backend and a React frontend, and owns both in production."
            ),
            job_requirements=(
                "Strong Python. Production experience with FastAPI and React. "
                "Comfortable owning features end to end."
            ),
            expected_match_range=(0.7, 0.95),
            expected_matched_skills=["FastAPI", "Python", "React"],
            expected_missing_skills=["PostgreSQL"],
        ),
        # No fit, and a trap for `_mentions`. None of the candidate's skills are
        # in this posting, but "MongoDB" contains "go" as a substring. If the
        # whole-token guard in the matcher regresses to a plain `in` check, "Go"
        # matches here and this case fails — which is the point of it.
        MatchingCase(
            candidate_skills=["Go", "Django", "jQuery"],
            job_title="Full Stack Engineer",
            job_description=(
                "Our product is a React single-page app backed by Node.js services "
                "and MongoDB."
            ),
            job_requirements=(
                "Solid React and Node.js. Familiarity with MongoDB. TypeScript preferred."
            ),
            expected_match_range=(0.0, 0.2),
            expected_matched_skills=[],
            expected_missing_skills=["Django", "Go", "jQuery"],
        ),
        # Partial fit: the shared language is evidenced, the frameworks are not.
        MatchingCase(
            candidate_skills=["Python", "PyTorch", "LangChain"],
            job_title="Machine Learning Engineer",
            job_description=(
                "You will take ranking models from notebook to production, serving "
                "traffic behind our search bar."
            ),
            job_requirements=(
                "Python. Production ML experience. TensorFlow in our serving stack."
            ),
            expected_match_range=(0.3, 0.6),
            expected_matched_skills=["Python"],
            expected_missing_skills=["LangChain", "PyTorch"],
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
