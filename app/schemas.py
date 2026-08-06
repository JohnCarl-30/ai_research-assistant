import re
import uuid
from datetime import datetime

from pydantic import BaseModel


class ScanRequest(BaseModel):
    query: str
    location: str = ""
    skills: list[str] = []


class ScanResponse(BaseModel):
    scan_id: str | None = None
    jobs_found: int = 0
    new_jobs: int = 0
    top_tags: list[dict] = []
    status: str
    error: str | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    title: str
    url: str
    source: str
    location: str | None = None
    salary_range: str | None = None
    is_easy_apply: bool = False
    company_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyResponse(BaseModel):
    id: uuid.UUID
    name: str
    domain: str | None = None
    mission: str | None = None
    tech_stack: str | None = None
    size: str | None = None
    funding_stage: str | None = None
    linkedin_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedJobs(BaseModel):
    items: list[JobResponse]
    total: int
    limit: int
    offset: int


class PaginatedCompanies(BaseModel):
    items: list[CompanyResponse]
    total: int
    limit: int
    offset: int


def normalize_location(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    return value.title()


class JobPatchRequest(BaseModel):
    title: str | None = None
    location: str | None = None
    salary_range: str | None = None
    description: str | None = None
    requirements: str | None = None
    is_easy_apply: bool | None = None
    company_id: uuid.UUID | None = None


class ReviewResponse(BaseModel):
    id: uuid.UUID
    rating: int
    pros: str | None = None
    cons: str | None = None
    job_title: str | None = None
    employment_status: str | None = None
    review_date: str | None = None
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SalaryResponse(BaseModel):
    id: uuid.UUID
    job_title: str
    salary_min: int | None = None
    salary_max: int | None = None
    location: str | None = None
    currency: str
    period: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TagResponse(BaseModel):
    tag: str
    count: int
    last_seen_at: datetime
    source_counts: dict | None = None
    type_counts: dict | None = None


class PaginatedTags(BaseModel):
    items: list[TagResponse]
    total: int
