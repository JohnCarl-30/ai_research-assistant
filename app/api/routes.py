import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.pipeline import run_pipeline
from app.agents.scraper import ScrapedJob
from app.database import get_db
from app.models import Company, CompanyReview, Job, SalaryData, TagCount
from app.schemas import (
    AskRequest,
    AskResponse,
    CompanyResponse,
    FirecrawlRequest,
    FirecrawlResponse,
    IndexRequest,
    IndexResponse,
    JobMatchResponse,
    JobPatchRequest,
    JobResponse,
    MatchRequest,
    MatchResponse,
    PaginatedCompanies,
    PaginatedJobs,
    PaginatedTags,
    RetrievedChunkResponse,
    ReviewResponse,
    SalaryResponse,
    ScanRequest,
    ScanResponse,
    SearchResponse,
    TagResponse,
    normalize_location,
)

router = APIRouter()


@router.post("/scan", response_model=ScanResponse)
async def scan_jobs(req: ScanRequest):
    result = await run_pipeline(req.query, req.location, req.skills)
    return ScanResponse(
        scan_id=result.get("scan_id"),
        jobs_found=result.get("jobs_found", 0),
        new_jobs=result.get("new_jobs", 0),
        top_tags=result.get("top_tags", []),
        status=result.get("status", "pending"),
        error=result.get("error"),
    )


@router.get("/jobs", response_model=PaginatedJobs)
async def get_jobs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Job).options(selectinload(Job.company))
    count_query = select(func.count(Job.id))

    if source:
        query = query.where(Job.source == source)
        count_query = count_query.where(Job.source == source)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Job.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()

    items = [
        JobResponse(
            id=j.id,
            title=j.title,
            url=j.url,
            source=j.source,
            location=j.location,
            salary_range=j.salary_range,
            is_easy_apply=j.is_easy_apply,
            company_name=j.company.name if j.company else None,
            created_at=j.created_at,
        )
        for j in jobs
    ]

    return PaginatedJobs(items=items, total=total, limit=limit, offset=offset)


@router.patch("/jobs/{job_id}", response_model=JobResponse)
async def patch_job(
    job_id: uuid.UUID,
    req: JobPatchRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job).options(selectinload(Job.company)).where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    patch_data = req.model_dump(exclude_unset=True)
    if "location" in patch_data and patch_data["location"] is not None:
        patch_data["location"] = normalize_location(patch_data["location"])

    for field, value in patch_data.items():
        setattr(job, field, value)

    await db.flush()
    await db.refresh(job, ["company"])

    return JobResponse(
        id=job.id,
        title=job.title,
        url=job.url,
        source=job.source,
        location=job.location,
        salary_range=job.salary_range,
        is_easy_apply=job.is_easy_apply,
        company_name=job.company.name if job.company else None,
        created_at=job.created_at,
    )


@router.get("/companies", response_model=PaginatedCompanies)
async def get_companies(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    count_query = select(func.count(Company.id))
    total = (await db.execute(count_query)).scalar() or 0

    query = select(Company).order_by(Company.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    companies = result.scalars().all()

    items = [CompanyResponse.model_validate(c) for c in companies]

    return PaginatedCompanies(items=items, total=total, limit=limit, offset=offset)


@router.get("/companies/{company_id}/reviews", response_model=list[ReviewResponse])
async def get_company_reviews(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompanyReview)
        .where(CompanyReview.company_id == company_id)
        .order_by(CompanyReview.created_at.desc())
        .limit(10)
    )
    reviews = result.scalars().all()
    return [ReviewResponse.model_validate(r) for r in reviews]


@router.get("/companies/{company_id}/salary", response_model=list[SalaryResponse])
async def get_company_salary(
    company_id: uuid.UUID,
    job_title: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(SalaryData).where(SalaryData.company_id == company_id)
    if job_title:
        query = query.where(func.lower(SalaryData.job_title).contains(job_title.lower()))
    query = query.order_by(SalaryData.created_at.desc())
    result = await db.execute(query)
    salaries = result.scalars().all()
    return [SalaryResponse.model_validate(s) for s in salaries]


@router.get("/tags", response_model=PaginatedTags)
async def get_tags(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    count_query = select(func.count(TagCount.id))
    total = (await db.execute(count_query)).scalar() or 0

    query = select(TagCount).order_by(TagCount.count.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    tags = result.scalars().all()

    items = [
        TagResponse(
            tag=t.tag,
            count=t.count,
            last_seen_at=t.last_seen_at,
            source_counts=t.source_counts,
            type_counts=t.type_counts,
        )
        for t in tags
    ]

    return PaginatedTags(items=items, total=total)


@router.get("/tags/trending", response_model=PaginatedTags)
async def get_trending_tags(
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(UTC) - timedelta(days=days)

    count_query = select(func.count(TagCount.id)).where(TagCount.last_seen_at >= cutoff)
    total = (await db.execute(count_query)).scalar() or 0

    query = (
        select(TagCount)
        .where(TagCount.last_seen_at >= cutoff)
        .order_by(TagCount.count.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    tags = result.scalars().all()

    items = [
        TagResponse(
            tag=t.tag,
            count=t.count,
            last_seen_at=t.last_seen_at,
            source_counts=t.source_counts,
            type_counts=t.type_counts,
        )
        for t in tags
    ]

    return PaginatedTags(items=items, total=total)


@router.get("/cover-letter")
async def cover_letter(
    job_title: str,
    company_name: str,
    job_description: str = "",
    skills: str = "",
    stream: bool = False,
):
    from app.agents.cover_letter import generate_cover_letter

    user_skills = [s.strip() for s in skills.split(",") if s.strip()] if skills else None

    if stream:
        from app.agents.cover_letter_stream import (
            generate_cover_letter_stream,
        )

        return StreamingResponse(
            generate_cover_letter_stream(
                job_title=job_title,
                company_name=company_name,
                job_description=job_description or None,
                user_skills=user_skills,
            ),
            media_type="text/event-stream",
        )

    result = await generate_cover_letter(
        job_title=job_title,
        company_name=company_name,
        job_description=job_description or None,
        user_skills=user_skills,
    )
    return result


def _chunk_response(item) -> RetrievedChunkResponse:
    return RetrievedChunkResponse(
        job_id=item.chunk.job_id,
        job_title=item.chunk.job_title,
        company_name=item.chunk.company_name,
        job_url=item.chunk.job_url,
        section=item.chunk.section,
        content=item.chunk.content,
        score=item.score,
        dense_rank=item.dense_rank,
        sparse_rank=item.sparse_rank,
    )


@router.post("/rag/index", response_model=IndexResponse)
async def rag_index(req: IndexRequest, db: AsyncSession = Depends(get_db)):
    """Embed job postings into the vector store."""
    from app.rag.vector_store import index_jobs, unindexed_jobs

    if req.reindex_all:
        result = await db.execute(
            select(Job).options(selectinload(Job.company)).limit(req.limit)
        )
        jobs = list(result.scalars().all())
    else:
        jobs = await unindexed_jobs(db, limit=req.limit)

    chunks = await index_jobs(db, jobs)
    return IndexResponse(jobs_indexed=len(jobs), chunks_written=chunks)


@router.get("/rag/search", response_model=SearchResponse)
async def rag_search(
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=50),
    hybrid: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve job-posting chunks relevant to a query."""
    from app.rag.retriever import retrieve

    results = await retrieve(db, q, top_k=top_k, hybrid=hybrid)
    return SearchResponse(query=q, results=[_chunk_response(r) for r in results])


@router.post("/rag/ask", response_model=AskResponse)
async def rag_ask(req: AskRequest, db: AsyncSession = Depends(get_db)):
    """Answer a question grounded in the indexed job postings."""
    from app.rag.qa import answer_job_question

    result = await answer_job_question(db, req.question, top_k=req.top_k, hybrid=req.hybrid)
    return AskResponse(
        question=result.question,
        answer=result.answer,
        contexts=result.contexts,
        sources=[_chunk_response(r) for r in result.retrieved],
    )


@router.post("/rag/match", response_model=MatchResponse)
async def rag_match(req: MatchRequest, db: AsyncSession = Depends(get_db)):
    """Rank indexed jobs against a candidate's skills."""
    from app.rag.matcher import match_jobs

    matches = await match_jobs(db, req.skills, role=req.role, limit=req.limit)
    return MatchResponse(
        matches=[
            JobMatchResponse(
                job_id=m.job_id,
                title=m.title,
                company_name=m.company_name,
                url=m.url,
                score=m.score,
                matched_skills=m.matched_skills,
                missing_skills=m.missing_skills,
            )
            for m in matches
        ]
    )


@router.post("/scrape-firecrawl", response_model=FirecrawlResponse)
async def scrape_firecrawl(req: FirecrawlRequest):
    """Scrape job boards using Firecrawl LangGraph pipeline.

    Flow: search -> scrape -> parse -> persist -> index -> END

    To execute, POST with search_results and scraped_pages from Firecrawl MCP.
    """
    from app.agents.firecrawl_scraper import run_firecrawl_pipeline, build_search_queries

    # If no pre-fetched data, return queries for the caller to execute
    if not req.search_results and not req.scraped_pages:
        queries = build_search_queries(
            role=req.role,
            location=req.location,
            remote_only=req.remote_only,
        )
        return FirecrawlResponse(
            role=req.role,
            location=req.location,
            queries=queries,
            sources=["greenhouse.io", "ashbyhq.com", "lever.co"],
            status="ready",
            message="Execute these searches with Firecrawl MCP, then POST results back",
        )

    # Run the full pipeline with pre-fetched data
    result = await run_firecrawl_pipeline(
        role=req.role,
        location=req.location,
        remote_only=req.remote_only,
        max_results=req.max_results,
        search_results=req.search_results,
        scraped_pages=req.scraped_pages,
    )

    return FirecrawlResponse(
        role=req.role,
        location=req.location,
        queries=[],
        sources=["greenhouse.io", "ashbyhq.com", "lever.co"],
        status=result.get("status", "completed"),
        message=f"Found {result.get('jobs_found', 0)} jobs, indexed {result.get('new_jobs', 0)} new",
        scan_id=result.get("scan_id"),
        jobs_found=result.get("jobs_found", 0),
        new_jobs=result.get("new_jobs", 0),
    )
