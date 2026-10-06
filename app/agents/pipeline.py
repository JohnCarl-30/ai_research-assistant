"""LangGraph pipeline for job search automation.

Flow: scrape -> extract -> research -> cover_letters -> persist -> index -> END
"""

import uuid
from collections import Counter
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from scout_mcp.sources.http import Fetcher
from sqlalchemy import select

from app.agents.cover_letter import generate_cover_letter
from app.agents.researcher import research_company
from app.agents.scraper import JobScraper, ScrapedJob
from app.database import async_session
from app.models import (
    CompanyReview,
    JobTag,
    SalaryData,
    TagCount,
)
from app.rag.vector_store import index_jobs, unindexed_jobs
from app.services.persistence import (
    complete_scan,
    start_scan,
    upsert_company,
    upsert_job,
)
from app.services.tags import extract_source_tags, extract_tags


class PipelineState(TypedDict):
    """TypedDict state for LangGraph pipeline."""
    query: str
    location: str
    user_skills: Annotated[list[str], lambda x, y: x + y]
    jobs: list[ScrapedJob]
    companies_researched: dict
    cover_letters: dict
    new_companies: list[str]
    status: str
    error: str | None
    scan_id: str | None
    jobs_found: int
    new_jobs: int
    reviews: list[dict]
    salaries: list[dict]
    top_tags: list[dict]
    chunks_indexed: int
    messages: Annotated[list[dict], add_messages]


async def scrape_jobs(state: PipelineState) -> dict:
    """Scrape job boards for listings."""
    try:
        scraper = JobScraper()
        result = await scraper.scrape_all(state.get("query", ""), state.get("location", ""))
        jobs, reviews, salaries = result
        return {
            "jobs": jobs,
            "reviews": reviews,
            "salaries": salaries,
            "status": "scraped",
            "jobs_found": len(jobs),
        }
    except Exception as e:
        return {"error": str(e), "status": "failed", "jobs_found": 0}


def after_scrape(state: PipelineState) -> str:
    """Route after scraping based on results."""
    if state.get("error") or state.get("status") == "failed":
        return "persist"
    if not state.get("jobs"):
        return "persist"
    return "extract"


async def extract_companies(state: PipelineState) -> dict:
    """Extract unique company names from jobs."""
    companies = {}
    for job in state.get("jobs", []):
        if job.company not in companies:
            companies[job.company] = job.url
    return {"new_companies": list(companies.keys())}


async def research_companies(state: PipelineState) -> dict:
    """Research each company: Scout's dossier, summarised by an LLM."""
    results = {}
    fetcher = Fetcher()
    for company_name in state.get("new_companies", [])[:10]:
        try:
            results[company_name] = await research_company(company_name, fetcher=fetcher)
        except Exception as e:
            results[company_name] = {"error": str(e)}
    return {"companies_researched": results, "status": "researched"}


async def generate_cover_letters(state: PipelineState) -> dict:
    """Generate cover letters for top jobs."""
    cover_letters = {}
    for job in state.get("jobs", [])[:5]:
        try:
            result = await generate_cover_letter(
                job_title=job.title,
                company_name=job.company,
                job_description=job.description,
                requirements=None,
                user_skills=state.get("user_skills", []) or None,
            )
            cover_letters[job.url] = result
        except Exception as e:
            cover_letters[job.url] = {"error": str(e)}
    return {"cover_letters": cover_letters, "status": "completed"}


async def persist_results(state: PipelineState) -> dict:
    """Persist results to database."""
    from datetime import UTC, datetime

    scan_id = None
    new_jobs = 0
    top_tags: list[dict] = []
    tag_counter: Counter = Counter()
    tag_source_counts: dict[str, Counter] = {}
    tag_type_counts: dict[str, Counter] = {}

    try:
        async with async_session() as session:
            scan = await start_scan(session, state.get("query", ""))
            scan_id = str(scan.id)

            company_name_to_id: dict[str, uuid.UUID] = {}

            for company_name, research in state.get("companies_researched", {}).items():
                mission = None
                if isinstance(research, dict):
                    mission = research.get("summary") or research.get("raw_response")
                    if isinstance(mission, str) and len(mission) > 2000:
                        mission = mission[:2000]
                company = await upsert_company(session, company_name, mission=mission)
                company_name_to_id[company_name] = company.id

            for job_data in state.get("jobs", []):
                company_id = company_name_to_id.get(job_data.company)

                extracted = extract_tags(job_data.description or "") + extract_tags(
                    job_data.title or ""
                )
                extracted = list(dict.fromkeys(extracted))

                source = extract_source_tags(job_data.source_tags)

                job, is_new = await upsert_job(
                    session,
                    title=job_data.title,
                    url=job_data.url,
                    source=job_data.source,
                    location=job_data.location,
                    salary_range=job_data.salary,
                    description=job_data.description,
                    is_easy_apply=job_data.is_easy_apply,
                    company_id=company_id,
                )
                if is_new:
                    new_jobs += 1

                    for tag in extracted:
                        jt = JobTag(job_id=job.id, tag=tag, tag_type="extracted")
                        session.add(jt)
                        tag_counter[tag] += 1
                        tag_source_counts.setdefault(tag, Counter())
                        tag_source_counts[tag][job_data.source] += 1
                        tag_type_counts.setdefault(tag, Counter())
                        tag_type_counts[tag]["extracted"] += 1

                    for tag in source:
                        jt = JobTag(job_id=job.id, tag=tag, tag_type="source")
                        session.add(jt)
                        tag_counter[tag] += 1
                        tag_source_counts.setdefault(tag, Counter())
                        tag_source_counts[tag][job_data.source] += 1
                        tag_type_counts.setdefault(tag, Counter())
                        tag_type_counts[tag]["source"] += 1

            for review_data in state.get("reviews", []):
                company_name = review_data.get("company")
                company_id = company_name_to_id.get(company_name)
                if company_id:
                    review = CompanyReview(
                        company_id=company_id,
                        rating=review_data.get("rating", 0),
                        pros=review_data.get("pros"),
                        cons=review_data.get("cons"),
                        job_title=review_data.get("job_title"),
                        employment_status=review_data.get("employment_status"),
                        review_date=review_data.get("review_date"),
                        source=review_data.get("source", "glassdoor"),
                    )
                    session.add(review)

            for salary_data in state.get("salaries", []):
                company_name = salary_data.get("company")
                company_id = company_name_to_id.get(company_name)
                if company_id:
                    salary = SalaryData(
                        company_id=company_id,
                        job_title=salary_data.get("job_title", ""),
                        salary_min=None,
                        salary_max=None,
                        location=None,
                        source=salary_data.get("source", "glassdoor"),
                    )
                    session.add(salary)

            for tag, count in tag_counter.most_common(10):
                result = await session.execute(select(TagCount).where(TagCount.tag == tag))
                existing = result.scalar_one_or_none()
                if existing:
                    existing.count += count
                    existing.last_seen_at = datetime.now(UTC)
                    sc = existing.source_counts or {}
                    for src, cnt in tag_source_counts[tag].items():
                        sc[src] = sc.get(src, 0) + cnt
                    existing.source_counts = sc
                    tc = existing.type_counts or {}
                    for tt, cnt in tag_type_counts[tag].items():
                        tc[tt] = tc.get(tt, 0) + cnt
                    existing.type_counts = tc
                else:
                    tc = TagCount(
                        tag=tag,
                        count=count,
                        last_seen_at=datetime.now(UTC),
                        source_counts=dict(tag_source_counts[tag]),
                        type_counts=dict(tag_type_counts[tag]),
                    )
                    session.add(tc)

                top_tags.append({"tag": tag, "count": count})

            status = "completed" if not state.get("error") else "failed"
            await complete_scan(
                session,
                scan,
                jobs_found=state.get("jobs_found", 0),
                new_jobs=new_jobs,
                status=status,
                error=state.get("error"),
            )
            await session.commit()
    except Exception as e:
        return {"error": str(e), "status": "failed"}

    return {
        "scan_id": scan_id,
        "new_jobs": new_jobs,
        "top_tags": top_tags,
        "status": "completed" if not state.get("error") else "failed",
    }


async def index_jobs_for_rag(state: PipelineState) -> dict:
    """Embed newly persisted jobs so they are searchable."""
    if state.get("status") == "failed":
        return {"chunks_indexed": 0}

    try:
        async with async_session() as session:
            jobs = await unindexed_jobs(session, limit=100)
            chunks = await index_jobs(session, jobs)
            await session.commit()
        return {"chunks_indexed": chunks}
    except Exception:
        return {"chunks_indexed": 0}


# Build the workflow
workflow = StateGraph(PipelineState)

workflow.add_node("scrape", scrape_jobs)
workflow.add_node("extract", extract_companies)
workflow.add_node("research", research_companies)
workflow.add_node("cover_letters", generate_cover_letters)
workflow.add_node("persist", persist_results)
workflow.add_node("index", index_jobs_for_rag)

workflow.set_entry_point("scrape")
workflow.add_conditional_edges(
    "scrape",
    after_scrape,
    {
        "extract": "extract",
        "persist": "persist",
    },
)
workflow.add_edge("extract", "research")
workflow.add_edge("research", "cover_letters")
workflow.add_edge("cover_letters", "persist")
workflow.add_edge("persist", "index")
workflow.add_edge("index", END)

graph = workflow.compile()


async def run_pipeline(
    query: str,
    location: str = "",
    user_skills: list[str] | None = None,
) -> dict:
    """Run the full pipeline."""
    initial_state = PipelineState(
        query=query,
        location=location,
        user_skills=user_skills or [],
        jobs=[],
        companies_researched={},
        cover_letters={},
        new_companies=[],
        status="pending",
        error=None,
        scan_id=None,
        jobs_found=0,
        new_jobs=0,
        reviews=[],
        salaries=[],
        top_tags=[],
        chunks_indexed=0,
        messages=[],
    )
    result = await graph.ainvoke(initial_state)
    return {
        "scan_id": result.get("scan_id"),
        "jobs": [vars(j) if hasattr(j, "__dict__") else j for j in result.get("jobs", [])],
        "companies": result.get("companies_researched", {}),
        "cover_letters": result.get("cover_letters", {}),
        "jobs_found": result.get("jobs_found", 0),
        "new_jobs": result.get("new_jobs", 0),
        "top_tags": result.get("top_tags", []),
        "status": result.get("status"),
    }
