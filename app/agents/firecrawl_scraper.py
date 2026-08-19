"""LangGraph pipeline for Firecrawl-based job scraping.

Flow: search -> scrape -> parse -> persist -> index -> END

Uses Firecrawl MCP tools to search and scrape company career pages
and ATS systems (Greenhouse, Ashby, Lever).
"""

import re
import uuid
from collections import Counter
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from sqlalchemy import select

from app.agents.scraper import ScrapedJob
from app.database import async_session
from app.models import JobTag, TagCount
from app.rag.vector_store import index_jobs, unindexed_jobs
from app.services.persistence import (
    complete_scan,
    start_scan,
    upsert_company,
    upsert_job,
)
from app.services.tags import extract_source_tags, extract_tags


# --- State ---


class FirecrawlState(TypedDict):
    """State for the Firecrawl scraping pipeline."""
    role: str
    location: str
    remote_only: bool
    max_results: int
    search_results: list[dict]
    job_urls: list[str]
    scraped_pages: list[dict]
    jobs: list[ScrapedJob]
    status: str
    error: str | None
    scan_id: str | None
    jobs_found: int
    new_jobs: int
    top_tags: list[dict]
    chunks_indexed: int
    messages: Annotated[list[dict], add_messages]


# --- Search Queries ---


def build_search_queries(
    role: str,
    location: str = "",
    remote_only: bool = False,
) -> list[dict]:
    """Build Firecrawl search queries for job sources.

    Sources from @SCR01111 tweet + ATS systems.
    """
    queries = []

    # --- ATS Systems (structured, reliable) ---
    queries.append({
        "query": f'site:greenhouse.io {role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["greenhouse.io"],
    })
    queries.append({
        "query": f'site:ashbyhq.com {role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["ashbyhq.com"],
    })
    queries.append({
        "query": f'site:lever.co {role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["lever.co"],
    })

    # --- Job Boards (from tweet) ---
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["wellfound.com"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["workatastartup.com"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["ottajobs.io"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["remoteok.com"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["weworkremotely.com"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["flexjobs.com"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["turing.com"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["arc.dev"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["hired.com"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["instahyre.com"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["cutshort.io"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["himalayas.app"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["dice.com"],
    })
    queries.append({
        "query": f'{role} jobs {location}'.strip(),
        "limit": 10,
        "includeDomains": ["startups.jobs"],
    })

    # --- General search (catches career pages) ---
    queries.append({
        "query": f'{role} engineer careers page {location} apply'.strip(),
        "limit": 10,
    })

    return queries


# --- Parse Helpers ---


def _extract_from_markdown(markdown: str, url: str, metadata: dict) -> ScrapedJob | None:
    """Parse Firecrawl markdown output into a ScrapedJob."""
    if not markdown:
        return None

    lines = markdown.strip().split("\n")
    title = None
    company = None
    location = None
    description_parts = []

    # Extract title from og:title
    if metadata.get("ogTitle"):
        title_match = re.search(r"^(.+?)(?:\s*(?:\||@|-)\s*)", metadata["ogTitle"])
        if title_match:
            title = title_match.group(1).strip()

    # Parse markdown
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("!["):
            continue

        # Title from first heading
        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
            continue

        # Company
        if re.match(r"^\*\*?(company|employer)\*\*?:?\s*", stripped, re.I):
            company = re.sub(r"^\*\*?(company|employer)\*\*?:?\s*", "", stripped, flags=re.I).strip()
            continue

        # Location
        if re.match(r"^\*\*?(city|location|remote)\*\*?:?\s*", stripped, re.I):
            location = re.sub(r"^\*\*?(city|location|remote)\*\*?:?\s*", "", stripped, flags=re.I).strip()
            continue

        # Collect description
        if title and not stripped.startswith("#"):
            if re.match(r"^(apply|submit|apply now)", stripped, re.I):
                break
            description_parts.append(stripped)

    # Extract company from URL if not found
    if not company:
        gh_match = re.search(r"greenhouse\.io/([^/]+)/jobs/", url)
        if gh_match:
            company = gh_match.group(1).replace("-", " ").title()
        ashby_match = re.search(r"ashbyhq\.com/([^/]+)/", url)
        if ashby_match:
            company = ashby_match.group(1).replace("-", " ").title()

    # Clean description
    description = "\n".join(description_parts[:50]) if description_parts else None
    if description:
        description = re.sub(r"\*\*(.+?)\*\*", r"\1", description)
        description = re.sub(r"#{1,6}\s*", "", description)
        description = description[:2000]

    if not title:
        return None

    return ScrapedJob(
        title=title,
        url=url,
        company=company or "Unknown",
        location=location,
        description=description,
        source="firecrawl",
    )


# --- Pipeline Nodes ---


async def search_jobs(state: FirecrawlState) -> dict:
    """Search for jobs using Firecrawl search queries.

    NOTE: This node returns search queries. The actual Firecrawl MCP calls
    must be executed by the caller or a middleware that has access to the
    Firecrawl MCP tools.
    """
    queries = build_search_queries(
        role=state.get("role", ""),
        location=state.get("location", ""),
        remote_only=state.get("remote_only", False),
    )

    # Collect all job URLs from search results
    all_urls = []
    all_results = []

    # In production, these would be Firecrawl MCP tool calls
    # For now, we store the queries and expect results to be injected
    search_results = state.get("search_results", [])

    for result in search_results:
        url = result.get("url", "")
        if url and url not in all_urls:
            all_urls.append(url)
            all_results.append(result)

    return {
        "search_results": all_results,
        "job_urls": all_urls[:state.get("max_results", 25)],
        "status": "searched",
    }


async def scrape_jobs(state: FirecrawlState) -> dict:
    """Scrape job pages using Firecrawl.

    NOTE: This node returns scrape URLs. The actual Firecrawl MCP calls
    must be executed by the caller or a middleware.
    """
    urls = state.get("job_urls", [])
    if not urls:
        return {"scraped_pages": [], "status": "no_urls"}

    # In production, these would be Firecrawl MCP scrape calls
    # For now, we expect scraped content to be injected
    scraped_pages = state.get("scraped_pages", [])

    return {
        "scraped_pages": scraped_pages,
        "status": "scraped",
    }


def after_scrape(state: FirecrawlState) -> str:
    """Route after scraping based on results."""
    if state.get("error") or state.get("status") == "failed":
        return "persist"
    if not state.get("scraped_pages"):
        return "persist"
    return "parse"


async def parse_jobs(state: FirecrawlState) -> dict:
    """Parse scraped pages into ScrapedJob objects."""
    jobs = []

    for page in state.get("scraped_pages", []):
        markdown = page.get("markdown", "")
        url = page.get("url", "")
        metadata = page.get("metadata", {})

        job = _extract_from_markdown(markdown, url, metadata)
        if job:
            jobs.append(job)

    return {
        "jobs": jobs,
        "jobs_found": len(jobs),
        "status": "parsed",
    }


async def persist_jobs(state: FirecrawlState) -> dict:
    """Persist scraped jobs to database."""
    from datetime import UTC, datetime

    scan_id = None
    new_jobs = 0
    top_tags: list[dict] = []
    tag_counter: Counter = Counter()

    try:
        async with async_session() as session:
            scan = await start_scan(session, state.get("role", ""))
            scan_id = str(scan.id)

            company_name_to_id: dict[str, uuid.UUID] = {}

            for job_data in state.get("jobs", []):
                # Upsert company
                if job_data.company not in company_name_to_id:
                    company = await upsert_company(session, job_data.company)
                    company_name_to_id[job_data.company] = company.id

                company_id = company_name_to_id.get(job_data.company)

                # Extract tags
                extracted = extract_tags(job_data.description or "") + extract_tags(
                    job_data.title or ""
                )
                extracted = list(dict.fromkeys(extracted))

                # Upsert job
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

            # Update tag counts
            for tag, count in tag_counter.most_common(10):
                result = await session.execute(select(TagCount).where(TagCount.tag == tag))
                existing = result.scalar_one_or_none()
                if existing:
                    existing.count += count
                    existing.last_seen_at = datetime.now(UTC)
                else:
                    tc = TagCount(
                        tag=tag,
                        count=count,
                        last_seen_at=datetime.now(UTC),
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


async def index_jobs_for_rag(state: FirecrawlState) -> dict:
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


# --- Build the Workflow ---


workflow = StateGraph(FirecrawlState)

workflow.add_node("search", search_jobs)
workflow.add_node("scrape", scrape_jobs)
workflow.add_node("parse", parse_jobs)
workflow.add_node("persist", persist_jobs)
workflow.add_node("index", index_jobs_for_rag)

workflow.set_entry_point("search")
workflow.add_edge("search", "scrape")
workflow.add_conditional_edges(
    "scrape",
    after_scrape,
    {
        "parse": "parse",
        "persist": "persist",
    },
)
workflow.add_edge("parse", "persist")
workflow.add_edge("persist", "index")
workflow.add_edge("index", END)

graph = workflow.compile()


async def run_firecrawl_pipeline(
    role: str,
    location: str = "",
    remote_only: bool = False,
    max_results: int = 25,
    search_results: list[dict] | None = None,
    scraped_pages: list[dict] | None = None,
) -> dict:
    """Run the Firecrawl scraping pipeline.

    Args:
        role: Job role to search for (e.g., "python engineer")
        location: Location filter
        remote_only: Only search remote jobs
        max_results: Maximum jobs to return
        search_results: Pre-fetched search results from Firecrawl MCP
        scraped_pages: Pre-fetched page content from Firecrawl MCP

    Returns:
        Pipeline results with jobs, scan_id, status, etc.
    """
    initial_state = FirecrawlState(
        role=role,
        location=location,
        remote_only=remote_only,
        max_results=max_results,
        search_results=search_results or [],
        job_urls=[],
        scraped_pages=scraped_pages or [],
        jobs=[],
        status="pending",
        error=None,
        scan_id=None,
        jobs_found=0,
        new_jobs=0,
        top_tags=[],
        chunks_indexed=0,
        messages=[],
    )
    result = await graph.ainvoke(initial_state)
    return {
        "scan_id": result.get("scan_id"),
        "jobs": [vars(j) if hasattr(j, "__dict__") else j for j in result.get("jobs", [])],
        "jobs_found": result.get("jobs_found", 0),
        "new_jobs": result.get("new_jobs", 0),
        "top_tags": result.get("top_tags", []),
        "status": result.get("status"),
    }
