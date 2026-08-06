import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, Job, ScanResult


async def start_scan(session: AsyncSession, query: str) -> ScanResult:
    scan = ScanResult(query=query, status="running")
    session.add(scan)
    await session.flush()
    return scan


async def upsert_company(
    session: AsyncSession,
    name: str,
    *,
    domain: str | None = None,
    mission: str | None = None,
    tech_stack: str | None = None,
    size: str | None = None,
    funding_stage: str | None = None,
    linkedin_url: str | None = None,
) -> Company:
    result = await session.execute(select(Company).where(Company.name == name))
    company = result.scalar_one_or_none()
    if company is not None:
        return company

    company = Company(
        name=name,
        domain=domain,
        mission=mission,
        tech_stack=tech_stack,
        size=size,
        funding_stage=funding_stage,
        linkedin_url=linkedin_url,
    )
    session.add(company)
    await session.flush()
    return company


async def upsert_job(
    session: AsyncSession,
    *,
    title: str,
    url: str,
    source: str,
    location: str | None = None,
    salary_range: str | None = None,
    description: str | None = None,
    requirements: str | None = None,
    is_easy_apply: bool = False,
    company_id: uuid.UUID | None = None,
) -> tuple[Job, bool]:
    """Return (job, is_new). is_new is False when the URL already existed."""
    if not url:
        return None, False

    result = await session.execute(select(Job).where(Job.url == url))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    job = Job(
        title=title,
        url=url,
        source=source,
        location=location,
        salary_range=salary_range,
        description=description,
        requirements=requirements,
        is_easy_apply=is_easy_apply,
        company_id=company_id,
    )
    session.add(job)
    await session.flush()
    return job, True


async def complete_scan(
    session: AsyncSession,
    scan: ScanResult,
    *,
    jobs_found: int,
    new_jobs: int,
    status: str = "completed",
    error: str | None = None,
) -> ScanResult:
    scan.jobs_found = jobs_found
    scan.new_jobs = new_jobs
    scan.status = status
    scan.error = error
    scan.completed_at = datetime.now(UTC)
    await session.flush()
    return scan
