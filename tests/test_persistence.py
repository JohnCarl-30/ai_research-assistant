import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.persistence import (
    complete_scan,
    start_scan,
    upsert_company,
    upsert_job,
)


@pytest.mark.asyncio
async def test_start_scan(session: AsyncSession):
    scan = await start_scan(session, "python developer")
    assert scan.id is not None
    assert scan.query == "python developer"
    assert scan.status == "running"


@pytest.mark.asyncio
async def test_upsert_company_new(session: AsyncSession):
    company = await upsert_company(session, "Acme Corp", mission="Build widgets")
    assert company.id is not None
    assert company.name == "Acme Corp"
    assert company.mission == "Build widgets"


@pytest.mark.asyncio
async def test_upsert_company_existing(session: AsyncSession):
    c1 = await upsert_company(session, "SameCo")
    c2 = await upsert_company(session, "SameCo")
    assert c1.id == c2.id


@pytest.mark.asyncio
async def test_upsert_job_new(session: AsyncSession):
    company = await upsert_company(session, "JobCo")
    job, is_new = await upsert_job(
        session,
        title="Engineer",
        url="https://example.com/job/1",
        source="linkedin",
        company_id=company.id,
    )
    assert is_new is True
    assert job.id is not None
    assert job.company_id == company.id


@pytest.mark.asyncio
async def test_upsert_job_duplicate_url(session: AsyncSession):
    await upsert_job(
        session,
        title="Engineer",
        url="https://example.com/job/2",
        source="linkedin",
    )
    job2, is_new = await upsert_job(
        session,
        title="Engineer (dup)",
        url="https://example.com/job/2",
        source="linkedin",
    )
    assert is_new is False


@pytest.mark.asyncio
async def test_upsert_job_empty_url(session: AsyncSession):
    job, is_new = await upsert_job(
        session,
        title="Engineer",
        url="",
        source="linkedin",
    )
    assert job is None
    assert is_new is False


@pytest.mark.asyncio
async def test_complete_scan(session: AsyncSession):
    scan = await start_scan(session, "test query")
    completed = await complete_scan(
        session,
        scan,
        jobs_found=10,
        new_jobs=5,
        status="completed",
    )
    assert completed.jobs_found == 10
    assert completed.new_jobs == 5
    assert completed.status == "completed"
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_complete_scan_with_error(session: AsyncSession):
    scan = await start_scan(session, "failing query")
    failed = await complete_scan(
        session,
        scan,
        jobs_found=0,
        new_jobs=0,
        status="failed",
        error="scrape timeout",
    )
    assert failed.status == "failed"
    assert failed.error == "scrape timeout"
