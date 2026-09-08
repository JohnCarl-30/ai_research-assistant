"""LLM-as-judge scoring for Scout agents.

Uses GPT-4o to evaluate agent outputs against defined criteria.
"""

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage


@dataclass
class ScoreResult:
    """Result from LLM judge."""
    score: float  # 0-1
    reasoning: str
    details: dict[str, Any] | None = None


async def _judge_with_llm(
    system_prompt: str,
    user_prompt: str,
    model: str = "gpt-4o",
) -> dict:
    """Call LLM judge and parse JSON response."""
    from langchain_openai import ChatOpenAI
    from app.config import get_settings

    settings = get_settings()
    llm = ChatOpenAI(model=model, temperature=0, api_key=settings.openai_api_key)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await llm.ainvoke(messages)

    # Parse JSON from response
    content = response.content
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        return {"score": 0.5, "reasoning": "Could not parse judge response"}


async def judge_cover_letter(
    cover_letter: str,
    job_title: str,
    company_name: str,
    job_description: str | None = None,
    user_skills: list[str] | None = None,
) -> ScoreResult:
    """Evaluate cover letter quality using LLM judge."""
    system_prompt = """You are an expert hiring manager evaluating cover letters.

Score the cover letter on these criteria (0-1 each):
1. RELEVANCE: Does it address the specific role and company?
2. SKILLS_MATCH: Does it highlight relevant skills?
3. TONE: Is it professional but personable?
4. CONCISENESS: Is it 3-4 paragraphs without fluff?
5. CALL_TO_ACTION: Does it end with a clear next step?

Output JSON:
{
    "score": <weighted_average 0-1>,
    "relevance": <0-1>,
    "skills_match": <0-1>,
    "tone": <0-1>,
    "conciseness": <0-1>,
    "call_to_action": <0-1>,
    "reasoning": "<brief explanation>"
}"""

    user_prompt = f"""Evaluate this cover letter:

Job Title: {job_title}
Company: {company_name}
Job Description: {job_description or "Not provided"}
User Skills: {', '.join(user_skills) if user_skills else "Not provided"}

Cover Letter:
{cover_letter}

Score this cover letter and provide detailed feedback."""

    result = await _judge_with_llm(system_prompt, user_prompt)

    return ScoreResult(
        score=result.get("score", 0.5),
        reasoning=result.get("reasoning", ""),
        details={
            "relevance": result.get("relevance", 0.5),
            "skills_match": result.get("skills_match", 0.5),
            "tone": result.get("tone", 0.5),
            "conciseness": result.get("conciseness", 0.5),
            "call_to_action": result.get("call_to_action", 0.5),
        },
    )


async def judge_research(
    research_result: dict,
    company_name: str,
) -> ScoreResult:
    """Evaluate company research quality using LLM judge."""
    system_prompt = """You are a talent intelligence analyst evaluating company research.

Score the research on these criteria (0-1 each):
1. COMPLETENESS: Are all fields populated (mission, tech_stack, size, funding)?
2. ACCURACY: Is the information factual and up-to-date?
3. USEFULNESS: Would this help a job seeker make a decision?
4. CONCISENESS: Is it brief but informative?

Output JSON:
{
    "score": <weighted_average 0-1>,
    "completeness": <0-1>,
    "accuracy": <0-1>,
    "usefulness": <0-1>,
    "conciseness": <0-1>,
    "reasoning": "<brief explanation>"
}"""

    user_prompt = f"""Evaluate this company research for {company_name}:

Research Result:
{json.dumps(research_result, indent=2)}

Score this research and provide detailed feedback."""

    result = await _judge_with_llm(system_prompt, user_prompt)

    return ScoreResult(
        score=result.get("score", 0.5),
        reasoning=result.get("reasoning", ""),
        details={
            "completeness": result.get("completeness", 0.5),
            "accuracy": result.get("accuracy", 0.5),
            "usefulness": result.get("usefulness", 0.5),
            "conciseness": result.get("conciseness", 0.5),
        },
    )


async def judge_matching(
    match_result: dict,
    candidate_skills: list[str],
    job_requirements: str,
) -> ScoreResult:
    """Evaluate job-candidate matching quality using LLM judge."""
    # The rubric is deliberately narrow. Scout's matcher retrieves postings and
    # reports which of the candidate's skills the posting evidences — it does
    # not infer transferable skills, write a recommendation, or explain itself.
    # An earlier rubric scored all three, so every run lost marks for output the
    # matcher is not designed to produce and the floor could never be met.
    system_prompt = """You are a senior technical recruiter evaluating a job matching system.

The system takes a candidate's skill list, retrieves job postings, and for each
posting reports which of those skills the posting evidences, which it does not,
a match_score (the fraction of the candidate's skills evidenced), and the rank
it gave that posting. It does not make recommendations — do not penalise it for
the absence of one.

Score on these criteria (0-1 each):
1. SKILL_IDENTIFICATION: Given the posting, are matched_skills and
   missing_skills correct? Penalise skills claimed as matched that the posting
   never mentions, and skills it does mention that were reported missing.
2. SCORE_CALIBRATION: Does match_score reflect the actual overlap?
3. RANKING: Is this posting's rank defensible for this candidate?

Output JSON:
{
    "score": <weighted_average 0-1>,
    "skill_identification": <0-1>,
    "score_calibration": <0-1>,
    "ranking": <0-1>,
    "reasoning": "<brief explanation>"
}"""

    user_prompt = f"""Evaluate this job-candidate match:

Candidate Skills: {', '.join(candidate_skills)}
Job Requirements: {job_requirements}

Match Result:
{json.dumps(match_result, indent=2)}

Score this matching result and provide detailed feedback."""

    result = await _judge_with_llm(system_prompt, user_prompt)

    return ScoreResult(
        score=result.get("score", 0.5),
        reasoning=result.get("reasoning", ""),
        details={
            "skill_identification": result.get("skill_identification", 0.5),
            "score_calibration": result.get("score_calibration", 0.5),
            "ranking": result.get("ranking", 0.5),
        },
    )
