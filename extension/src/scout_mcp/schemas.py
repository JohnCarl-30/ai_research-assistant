"""Result types for Scout's tools.

Declaring them gives clients a schema for each tool and the result as
structured data, alongside the JSON text older clients read. Sections whose
shape comes from outside sources stay open objects, described here.
"""

from typing import Any

from pydantic import BaseModel, Field

Section = dict[str, Any] | None


class SinceLastTime(BaseModel):
    previous_snapshot: str | None = Field(
        description="Date of the earlier research compared against, or null if this is the first."
    )
    changes: list[str] = Field(description="What changed, most important first.")


class Dossier(BaseModel):
    company: str
    domain: str | None = Field(description="The company's website domain, if known.")
    domain_source: str | None = Field(description='"given" or "wikidata".')
    facts: Section = Field(description="Wikidata: website, founded, employees, HQ, industry.")
    website: Section = Field(description="Tech fingerprint, about text, links found on the site.")
    dns: Section = Field(description="Email provider, email senders and verified SaaS tools.")
    hiring: Section = Field(
        description="Job board, open roles by team and location, remote share, tech in job posts."
    )
    github: Section = Field(description="GitHub org, languages, frameworks, activity, confidence.")
    hacker_news: Section = Field(description="Top and recent stories linking to the site.")
    saved_notes: list[dict[str, Any]] = Field(description="The user's notes about the company.")
    since_last_time: SinceLastTime | None = Field(
        default=None, description="Changes since Scout last researched this company."
    )
    gaps: list[str] = Field(description="What could not be found or reached.")
    next_steps: list[str] = Field(description="What to do next, e.g. use web search for news.")


class Changes(BaseModel):
    company: str
    domain: str | None
    previous_snapshot: str | None
    changes: list[str]
    open_roles: int | None = None
    gaps: list[str] = Field(default_factory=list)


class WatchlistCheck(BaseModel):
    checked: int
    results: list[Changes]


class WatchedCompany(BaseModel):
    company: str
    domain: str | None
    added_at: str


class Watchlist(BaseModel):
    companies: list[WatchedCompany]


class WatchResult(BaseModel):
    company: str
    domain: str | None
    watching: bool
    note: str


class Page(BaseModel):
    url: str
    title: str
    text: str
    truncated: bool


class GitHubResult(BaseModel):
    found: bool
    company: str
    profile: Section = Field(
        default=None, description="Org, languages, frameworks, repos, last push, confidence."
    )


class Note(BaseModel):
    id: int
    title: str
    content: str
    url: str | None
    tags: list[str]
    created_at: str


class NoteHit(BaseModel):
    id: int
    title: str
    url: str | None
    tags: list[str]
    snippet: str


class NoteSearch(BaseModel):
    results: list[NoteHit]


class NoteSummary(BaseModel):
    id: int
    title: str
    url: str | None
    tags: list[str]
    created_at: str


class NoteList(BaseModel):
    notes: list[NoteSummary]


class Deleted(BaseModel):
    deleted: int


class Export(BaseModel):
    folder: str
    written: int
    files: list[str]
