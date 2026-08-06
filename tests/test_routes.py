import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompanyReview, SalaryData, TagCount
from app.services.persistence import upsert_company, upsert_job


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    resp = await client.get("/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_jobs_empty(client: AsyncClient):
    resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_companies_empty(client: AsyncClient):
    resp = await client.get("/api/companies")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_post_scan_calls_pipeline(client: AsyncClient, monkeypatch):
    called_with = {}

    async def mock_run_pipeline(query, location="", user_skills=None):
        called_with["query"] = query
        return {
            "scan_id": "test-scan-id",
            "jobs": [],
            "companies": {},
            "cover_letters": {},
            "jobs_found": 0,
            "new_jobs": 0,
            "status": "completed",
        }

    monkeypatch.setattr("app.api.routes.run_pipeline", mock_run_pipeline)

    resp = await client.post("/api/scan", json={"query": "python", "location": "NYC"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_id"] == "test-scan-id"
    assert data["status"] == "completed"
    assert called_with["query"] == "python"


@pytest.mark.asyncio
async def test_get_jobs_with_params(client: AsyncClient):
    resp = await client.get("/api/jobs?limit=10&offset=0&source=linkedin")
    assert resp.status_code == 200
    data = resp.json()
    assert data["limit"] == 10
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_patch_job_location(client: AsyncClient, session: AsyncSession):
    company = await upsert_company(session, "PatchCo")
    job, _ = await upsert_job(
        session,
        title="Engineer",
        url="https://example.com/job/patch-1",
        source="linkedin",
        location="old location",
        company_id=company.id,
    )
    await session.commit()

    resp = await client.patch(
        f"/api/jobs/{job.id}",
        json={"location": "  san   francisco  "},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["location"] == "San Francisco"


@pytest.mark.asyncio
async def test_patch_job_title(client: AsyncClient, session: AsyncSession):
    job, _ = await upsert_job(
        session,
        title="Old Title",
        url="https://example.com/job/patch-2",
        source="indeed",
    )
    await session.commit()

    resp = await client.patch(
        f"/api/jobs/{job.id}",
        json={"title": "Senior Engineer"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Senior Engineer"


@pytest.mark.asyncio
async def test_patch_job_not_found(client: AsyncClient):
    resp = await client.patch(
        "/api/jobs/00000000-0000-0000-0000-000000000000",
        json={"location": "Remote"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_job_partial(client: AsyncClient, session: AsyncSession):
    job, _ = await upsert_job(
        session,
        title="Keep Title",
        url="https://example.com/job/patch-3",
        source="linkedin",
        location="Original Location",
    )
    await session.commit()

    resp = await client.patch(
        f"/api/jobs/{job.id}",
        json={"salary_range": "$100k-$150k"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Keep Title"
    assert data["location"] == "Original Location"
    assert data["salary_range"] == "$100k-$150k"


@pytest.mark.asyncio
async def test_get_company_reviews_empty(client: AsyncClient):
    resp = await client.get("/api/companies/00000000-0000-0000-0000-000000000000/reviews")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_company_reviews(client: AsyncClient, session: AsyncSession):
    company = await upsert_company(session, "ReviewCo")
    review = CompanyReview(
        company_id=company.id,
        rating=4,
        pros="Great culture",
        cons="Long hours",
        job_title="Engineer",
        employment_status="current",
        review_date="2024-01-01",
        source="glassdoor",
    )
    session.add(review)
    await session.commit()

    resp = await client.get(f"/api/companies/{company.id}/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["rating"] == 4
    assert data[0]["pros"] == "Great culture"


@pytest.mark.asyncio
async def test_get_company_salary_empty(client: AsyncClient):
    resp = await client.get("/api/companies/00000000-0000-0000-0000-000000000000/salary")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_company_salary(client: AsyncClient, session: AsyncSession):
    company = await upsert_company(session, "SalaryCo")
    salary = SalaryData(
        company_id=company.id,
        job_title="Software Engineer",
        salary_min=120000,
        salary_max=150000,
        location="NYC",
        currency="USD",
        period="yearly",
        source="glassdoor",
    )
    session.add(salary)
    await session.commit()

    resp = await client.get(f"/api/companies/{company.id}/salary")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["salary_min"] == 120000


@pytest.mark.asyncio
async def test_get_company_salary_filter(client: AsyncClient, session: AsyncSession):
    company = await upsert_company(session, "SalaryFilterCo")
    session.add(
        SalaryData(
            company_id=company.id,
            job_title="Software Engineer",
            salary_min=120000,
            salary_max=150000,
            source="glassdoor",
        )
    )
    session.add(
        SalaryData(
            company_id=company.id,
            job_title="Product Manager",
            salary_min=130000,
            salary_max=160000,
            source="glassdoor",
        )
    )
    await session.commit()

    resp = await client.get(
        f"/api/companies/{company.id}/salary",
        params={"job_title": "Engineer"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["job_title"] == "Software Engineer"


@pytest.mark.asyncio
async def test_get_tags_empty(client: AsyncClient):
    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_tags(client: AsyncClient, session: AsyncSession):
    session.add(TagCount(tag="python", count=10, source_counts={"linkedin": 5}))
    session.add(TagCount(tag="react", count=5, source_counts={"remote_ok": 3}))
    await session.commit()

    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["items"][0]["tag"] == "python"
    assert data["items"][0]["count"] == 10


@pytest.mark.asyncio
async def test_get_trending_tags(client: AsyncClient, session: AsyncSession):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete

    await session.execute(delete(TagCount))
    await session.commit()

    recent = datetime.now(UTC) - timedelta(days=1)
    old = datetime.now(UTC) - timedelta(days=10)

    session.add(TagCount(tag="trending-python", count=10, last_seen_at=recent))
    session.add(TagCount(tag="old-cobol", count=5, last_seen_at=old))
    await session.commit()

    resp = await client.get("/api/tags/trending", params={"days": 7})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["tag"] == "trending-python"
