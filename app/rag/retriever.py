"""Hybrid retrieval: dense vectors + BM25 keyword, fused with RRF.

Dense search handles paraphrase ("ML engineer" ~ "machine learning engineer");
BM25 handles the exact tokens dense models blur together (specific frameworks,
version numbers, seniority levels). Job search needs both — a query for "Rust"
must not return Go postings just because they are semantically adjacent.
"""

import re
import uuid
from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Job, JobChunk
from app.rag.embeddings import embed_query
from app.rag.vector_store import ScoredChunk, search, to_scored_chunk

# Standard RRF damping — keeps any single arm's top hit from dominating.
RRF_K = 60

_TOKEN = re.compile(r"[a-z0-9+#.]+")
# Not a full stop-word list; just the words that make a job query all-matching.
_STOPWORDS = frozenset(
    {"a", "an", "and", "are", "as", "at", "be", "for", "in", "is", "of", "on", "or",
     "that", "the", "to", "with", "what", "which", "who", "how", "any", "job", "jobs"}
)


@dataclass
class RetrievedChunk:
    chunk: ScoredChunk
    dense_rank: int | None
    sparse_rank: int | None
    score: float


def tokenize(text: str) -> list[str]:
    tokens = _TOKEN.findall(text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


async def _sparse_search(
    session: AsyncSession,
    query: str,
    limit: int,
    pool_size: int = 500,
) -> list[ScoredChunk]:
    """BM25 over chunks containing at least one query term.

    The SQL prefilter keeps the BM25 corpus bounded — scoring every chunk in the
    table in Python would not survive a real index.
    """
    terms = tokenize(query)
    if not terms:
        return []

    result = await session.execute(
        select(JobChunk)
        .options(selectinload(JobChunk.job).selectinload(Job.company))
        .where(or_(*[JobChunk.content.ilike(f"%{term}%") for term in terms]))
        .limit(pool_size)
    )
    candidates = list(result.scalars().all())
    if not candidates:
        return []

    bm25 = BM25Okapi([tokenize(c.content) for c in candidates])
    scores = bm25.get_scores(terms)

    # No score threshold. The prefilter means every candidate already contains a
    # query term, so BM25's IDF is computed over a biased pool and goes negative
    # for terms present in most of it — dropping non-positive scores would throw
    # away exactly the single-term queries the sparse arm exists to serve. Only
    # the ordering is consumed downstream (RRF fuses ranks, not scores).
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda p: p[1], reverse=True)
    return [to_scored_chunk(chunk, float(score)) for chunk, score in ranked[:limit]]


def reciprocal_rank_fusion(
    dense: list[ScoredChunk],
    sparse: list[ScoredChunk],
    limit: int,
) -> list[RetrievedChunk]:
    """Fuse two ranked lists by rank rather than score.

    Cosine similarity and BM25 are on incomparable scales, so RRF combines the
    positions instead of trying to normalise the raw numbers.
    """
    dense_ranks: dict[uuid.UUID, int] = {c.chunk_id: i for i, c in enumerate(dense)}
    sparse_ranks: dict[uuid.UUID, int] = {c.chunk_id: i for i, c in enumerate(sparse)}

    by_id: dict[uuid.UUID, ScoredChunk] = {c.chunk_id: c for c in sparse}
    by_id.update({c.chunk_id: c for c in dense})  # prefer dense's similarity score

    fused: list[RetrievedChunk] = []
    for chunk_id, chunk in by_id.items():
        d = dense_ranks.get(chunk_id)
        s = sparse_ranks.get(chunk_id)
        score = 0.0
        if d is not None:
            score += 1.0 / (RRF_K + d + 1)
        if s is not None:
            score += 1.0 / (RRF_K + s + 1)
        fused.append(RetrievedChunk(chunk=chunk, dense_rank=d, sparse_rank=s, score=score))

    fused.sort(key=lambda r: r.score, reverse=True)
    return fused[:limit]


async def retrieve(
    session: AsyncSession,
    query: str,
    top_k: int | None = None,
    *,
    hybrid: bool = True,
) -> list[RetrievedChunk]:
    """Retrieve the chunks most relevant to `query`."""
    settings = get_settings()
    top_k = top_k or settings.rag_top_k
    candidate_k = max(settings.rag_candidate_k, top_k)

    query_vector = await embed_query(query)
    dense = await search(session, query_vector, limit=candidate_k)

    if not hybrid:
        return [
            RetrievedChunk(chunk=c, dense_rank=i, sparse_rank=None, score=c.score)
            for i, c in enumerate(dense[:top_k])
        ]

    sparse = await _sparse_search(session, query, limit=candidate_k)
    return reciprocal_rank_fusion(dense, sparse, limit=top_k)
