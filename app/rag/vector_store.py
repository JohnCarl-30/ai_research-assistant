"""Persist and search job-posting chunk embeddings.

On PostgreSQL this pushes the nearest-neighbour search into pgvector. On any
other dialect (the SQLite test suite) it loads candidate vectors and scores them
in Python, so retrieval logic stays testable without a database server.
"""

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Job, JobChunk
from app.rag.chunking import chunk_job
from app.rag.embeddings import embed_texts


@dataclass
class ScoredChunk:
    chunk_id: uuid.UUID
    job_id: uuid.UUID
    job_title: str
    company_name: str | None
    job_url: str
    section: str
    content: str
    score: float


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def to_scored_chunk(chunk: JobChunk, score: float) -> ScoredChunk:
    job = chunk.job
    return ScoredChunk(
        chunk_id=chunk.id,
        job_id=chunk.job_id,
        job_title=job.title if job else "",
        company_name=job.company.name if job and job.company else None,
        job_url=job.url if job else "",
        section=chunk.section,
        content=chunk.content,
        score=score,
    )


async def index_job(session: AsyncSession, job: Job) -> int:
    """Re-chunk, embed and store one job. Returns the number of chunks written.

    Existing chunks for the job are replaced, so this is safe to re-run after a
    posting is edited or the embedding model changes.
    """
    return await index_jobs(session, [job])


async def index_jobs(session: AsyncSession, jobs: list[Job]) -> int:
    """Index many jobs in one embedding pass."""
    if not jobs:
        return 0

    settings = get_settings()

    pending: list[tuple[Job, list]] = []
    for job in jobs:
        chunks = chunk_job(
            title=job.title,
            company=job.company.name if job.company else None,
            location=job.location,
            salary=job.salary_range,
            description=job.description,
            requirements=job.requirements,
        )
        if chunks:
            pending.append((job, chunks))

    if not pending:
        return 0

    # One flat embedding call across every job beats one call per job.
    texts = [chunk.text for _, chunks in pending for chunk in chunks]
    vectors = await embed_texts(texts)

    await session.execute(
        delete(JobChunk).where(JobChunk.job_id.in_([job.id for job, _ in pending]))
    )

    cursor = 0
    written = 0
    for job, chunks in pending:
        for chunk in chunks:
            session.add(
                JobChunk(
                    job_id=job.id,
                    chunk_index=chunk.index,
                    section=chunk.section,
                    content=chunk.text,
                    embedding=vectors[cursor],
                    embedding_model=settings.embedding_model,
                )
            )
            cursor += 1
            written += 1

    await session.flush()
    return written


async def search(
    session: AsyncSession,
    query_embedding: list[float],
    limit: int = 10,
) -> list[ScoredChunk]:
    """Return the chunks nearest to `query_embedding`, best first.

    Scores are cosine similarity in [-1, 1]; higher is closer.
    """
    if not query_embedding:
        return []

    loader = selectinload(JobChunk.job).selectinload(Job.company)

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        distance = JobChunk.embedding.cosine_distance(query_embedding)
        result = await session.execute(
            select(JobChunk, distance.label("distance"))
            .options(loader)
            .where(JobChunk.embedding.is_not(None))
            .order_by(distance)
            .limit(limit)
        )
        return [to_scored_chunk(chunk, 1.0 - float(dist)) for chunk, dist in result.all()]

    # Portable fallback: score in Python.
    result = await session.execute(
        select(JobChunk).options(loader).where(JobChunk.embedding.is_not(None))
    )
    scored = [
        to_scored_chunk(chunk, cosine_similarity(query_embedding, list(chunk.embedding)))
        for chunk in result.scalars().all()
    ]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:limit]


async def fetch_job_chunks(
    session: AsyncSession,
    job_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[JobChunk]]:
    """All chunks for the given jobs, keyed by job id and ordered by position.

    Used to expand a chunk-level hit back to its whole posting: matching on the
    title chunk should not leave the answer-bearing body behind.
    """
    if not job_ids:
        return {}

    result = await session.execute(
        select(JobChunk)
        .options(selectinload(JobChunk.job).selectinload(Job.company))
        .where(JobChunk.job_id.in_(job_ids))
        .order_by(JobChunk.job_id, JobChunk.chunk_index)
    )

    grouped: dict[uuid.UUID, list[JobChunk]] = {}
    for chunk in result.scalars().all():
        grouped.setdefault(chunk.job_id, []).append(chunk)
    return grouped


async def unindexed_jobs(session: AsyncSession, limit: int = 100) -> list[Job]:
    """Jobs with no chunks, or whose chunks came from a different model."""
    settings = get_settings()

    current = select(JobChunk.job_id).where(JobChunk.embedding_model == settings.embedding_model)
    result = await session.execute(
        select(Job)
        .options(selectinload(Job.company))
        .where(Job.id.not_in(current))
        .order_by(Job.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
