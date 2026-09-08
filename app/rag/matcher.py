"""Rank indexed jobs against a candidate's skills."""

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.retriever import retrieve


@dataclass
class JobMatch:
    job_id: uuid.UUID
    title: str
    company_name: str | None
    url: str
    score: float
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


def _mentions(text: str, skill: str) -> bool:
    """Whole-token check, so "go" does not match "Django" and "r" not "React"."""
    return re.search(rf"(?<![a-z0-9]){re.escape(skill)}(?![a-z0-9])", text) is not None


def build_profile_query(skills: list[str], role: str | None = None) -> str:
    """Turn a skill list into prose, which embeds far better than a CSV line."""
    skills_text = ", ".join(s.strip() for s in skills if s.strip())
    role_text = role.strip() if role else "software engineer"
    return (
        f"A {role_text} with hands-on experience in {skills_text}. "
        f"Looking for a role using {skills_text}."
    )


async def match_jobs(
    session: AsyncSession,
    skills: list[str],
    role: str | None = None,
    limit: int = 10,
    *,
    chunks_per_job: int = 3,
) -> list[JobMatch]:
    """Return jobs ranked by fit against `skills`.

    Retrieval works on chunks, so several hits can belong to one job. A job's
    score is its best chunk — averaging would penalise long postings whose
    irrelevant sections drag the mean down.
    """
    if not skills:
        return []

    query = build_profile_query(skills, role)
    # Over-fetch: `limit` distinct jobs needs more than `limit` chunks.
    retrieved = await retrieve(session, query, top_k=limit * chunks_per_job)

    wanted = {s.strip().lower() for s in skills if s.strip()}
    by_job: dict[uuid.UUID, JobMatch] = {}

    for item in retrieved:
        chunk = item.chunk
        match = by_job.get(chunk.job_id)
        if match is None:
            match = JobMatch(
                job_id=chunk.job_id,
                title=chunk.job_title,
                company_name=chunk.company_name,
                url=chunk.job_url,
                score=item.score,
            )
            by_job[chunk.job_id] = match
        else:
            match.score = max(match.score, item.score)

        if len(match.evidence) < chunks_per_job:
            match.evidence.append(chunk.content)

    for match in by_job.values():
        evidence_text = "\n".join(match.evidence).lower()
        found = {s for s in wanted if _mentions(evidence_text, s)}
        match.matched_skills = sorted(found)
        match.missing_skills = sorted(wanted - found)

    ranked = sorted(by_job.values(), key=lambda m: m.score, reverse=True)
    return ranked[:limit]
