"""Hiring signals from public job boards: Greenhouse, Lever and Ashby.

All three publish a company's open roles as keyless JSON. The board name is
usually the company's slug; when the company's own site links to its board,
that exact name is used instead of a guess.

Job descriptions name the tools a team actually uses, so they are also a tech
stack source that does not depend on the company publishing code.
"""

import html
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Literal

from bs4 import BeautifulSoup

from scout_mcp.sources.http import HOUR, Fetcher, FetchError

Board = Literal["greenhouse", "lever", "ashby"]

BOARD_URLS: dict[Board, str] = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}

# Links on a company's site that name its board exactly.
BOARD_LINKS: dict[Board, re.Pattern] = {
    "greenhouse": re.compile(
        r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)"
    ),
    "lever": re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"),
}

# (label, pattern, case-sensitive). Ambiguous English words are matched
# case-sensitively ("React" not "react to", "Go" not "go-to-market").
TECH_TERMS: list[tuple[str, str, bool]] = [
    ("TypeScript", r"typescript", False), ("JavaScript", r"javascript", False),
    ("Python", r"python", False), ("Java", r"Java(?!Script)", True),
    ("Go", r"Golang|Go(?![- ]to\b)(?=[\s,/).])", True), ("Rust", r"Rust", True),
    ("Ruby", r"Ruby", True), ("Rails", r"Rails", True), ("Kotlin", r"kotlin", False),
    ("Swift", r"Swift", True), ("Scala", r"scala", False), ("Elixir", r"elixir", False),
    ("C++", r"C\+\+", True), ("C#", r"C#", True), ("PHP", r"PHP", True),
    ("React", r"React(?! Native| to\b| quickly\b)", True), ("React Native", r"React Native", True),
    ("Next.js", r"Next\.?js", False), ("Vue", r"Vue(?:\.js)?", True),
    ("Angular", r"Angular", True), ("Svelte", r"svelte", False),
    ("Node.js", r"node\.?js", False), ("GraphQL", r"graphql", False),
    ("Django", r"django", False), ("FastAPI", r"fastapi", False), ("Flask", r"Flask", True),
    ("Spring Boot", r"spring boot", False), ("PostgreSQL", r"postgres(?:ql)?", False),
    ("MySQL", r"mysql", False), ("MongoDB", r"mongodb", False), ("Redis", r"redis", False),
    ("Kafka", r"kafka", False), ("Elasticsearch", r"elasticsearch", False),
    ("Snowflake", r"Snowflake", True), ("BigQuery", r"bigquery", False),
    ("ClickHouse", r"clickhouse", False), ("dbt", r"dbt", True), ("Spark", r"Spark", True),
    ("AWS", r"AWS", True), ("GCP", r"GCP|Google Cloud", True), ("Azure", r"Azure", True),
    ("Kubernetes", r"kubernetes|k8s", False), ("Docker", r"docker", False),
    ("Terraform", r"terraform", False), ("PyTorch", r"pytorch", False),
    ("TensorFlow", r"tensorflow", False), ("LLMs", r"LLMs?", True),
]
_TECH = [
    (label, re.compile(rf"(?<![\w+#.]){pattern}(?![\w+#])", 0 if cs else re.I))
    for label, pattern, cs in TECH_TERMS
]


class JobBoardsUnavailableError(RuntimeError):
    """No board was found, and at least one job board service couldn't be reached."""


@dataclass
class Job:
    title: str
    department: str | None
    location: str | None
    remote: bool
    url: str | None
    text: str  # plain-text description, for tech extraction only


@dataclass
class Hiring:
    board: Board
    slug: str
    board_source: Literal["website", "guess"]
    open_roles: int
    by_department: list[tuple[str, int]] = field(default_factory=list)
    by_location: list[tuple[str, int]] = field(default_factory=list)
    remote_share: float | None = None
    tech_mentions: list[tuple[str, int]] = field(default_factory=list)
    sample_roles: list[dict] = field(default_factory=list)
    board_url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _plain(markup: str | None) -> str:
    if not markup:
        return ""
    return BeautifulSoup(html.unescape(markup), "html.parser").get_text(" ", strip=True)


def parse_greenhouse(data: dict) -> list[Job]:
    jobs = []
    for j in data.get("jobs", []):
        location = (j.get("location") or {}).get("name")
        departments = [d.get("name") for d in j.get("departments") or [] if d.get("name")]
        jobs.append(Job(
            title=j.get("title", ""),
            department=departments[0] if departments else None,
            location=location,
            remote="remote" in (location or "").lower(),
            url=j.get("absolute_url"),
            text=_plain(j.get("content")),
        ))
    return jobs


def parse_lever(data: list) -> list[Job]:
    jobs = []
    for j in data if isinstance(data, list) else []:
        cat = j.get("categories") or {}
        lists = " ".join(
            f"{x.get('text', '')} {_plain(x.get('content'))}" for x in j.get("lists") or []
        )
        location = cat.get("location") or ""
        jobs.append(Job(
            title=j.get("text", ""),
            department=cat.get("team") or cat.get("department"),
            location=cat.get("location"),
            remote=j.get("workplaceType") == "remote" or "remote" in location.lower(),
            url=j.get("hostedUrl"),
            text=f"{j.get('descriptionPlain', '')} {lists}",
        ))
    return jobs


def parse_ashby(data: dict) -> list[Job]:
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        jobs.append(Job(
            title=j.get("title", ""),
            department=j.get("department") or j.get("team"),
            location=j.get("location"),
            remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote",
            url=j.get("jobUrl"),
            text=j.get("descriptionPlain") or _plain(j.get("descriptionHtml")),
        ))
    return jobs


PARSERS = {"greenhouse": parse_greenhouse, "lever": parse_lever, "ashby": parse_ashby}
BOARD_PAGES = {
    "greenhouse": "https://job-boards.greenhouse.io/{slug}",
    "lever": "https://jobs.lever.co/{slug}",
    "ashby": "https://jobs.ashbyhq.com/{slug}",
}


def tech_mentions(jobs: list[Job]) -> list[tuple[str, int]]:
    """How many roles mention each technology (a role counts once per term)."""
    counts: Counter = Counter()
    for job in jobs:
        counts.update({label for label, rx in _TECH if rx.search(job.text)})
    return counts.most_common(15)


def summarize(board: Board, slug: str, source: str, jobs: list[Job]) -> Hiring:
    return Hiring(
        board=board,
        slug=slug,
        board_source=source,
        open_roles=len(jobs),
        by_department=Counter(j.department or "Unspecified" for j in jobs).most_common(8),
        by_location=Counter(j.location or "Unspecified" for j in jobs).most_common(6),
        remote_share=round(sum(j.remote for j in jobs) / len(jobs), 2) if jobs else None,
        tech_mentions=tech_mentions(jobs),
        sample_roles=[
            {"title": j.title, "department": j.department, "location": j.location, "url": j.url}
            for j in jobs[:10]
        ],
        board_url=BOARD_PAGES[board].format(slug=slug),
    )


def boards_linked(html_text: str) -> list[tuple[Board, str]]:
    """Job boards a page links to, as (board, slug)."""
    found: list[tuple[Board, str]] = []
    for board, rx in BOARD_LINKS.items():
        for slug in rx.findall(html_text):
            if slug.lower() not in {"embed", "api", "v1"} and (board, slug) not in found:
                found.append((board, slug))
    return found


async def fetch_board(fetcher: Fetcher, board: Board, slug: str) -> list[Job] | None:
    """The board's jobs, or None if this company has no such board."""
    try:
        data = await fetcher.get_json(BOARD_URLS[board].format(slug=slug), ttl=6 * HOUR)
    except FetchError as e:
        if e.status in (404, 400, 422):
            return None
        raise
    jobs = PARSERS[board](data)
    # Lever answers unknown boards with an empty list rather than a 404.
    return jobs or None


async def find_hiring(
    fetcher: Fetcher, linked: list[tuple[Board, str]], guesses: list[str]
) -> Hiring | None:
    """Try boards the company's site links to first, then slug guesses.

    One board being down must not hide another, so each attempt fails on its
    own. Only when nothing was found and some attempts failed is that an
    error (the board may exist on a service that was unreachable).
    """
    attempts = [(b, s, "website") for b, s in linked]
    attempts += [(b, s, "guess") for s in guesses for b in BOARD_URLS if (b, s) not in linked]
    errors: list[str] = []
    for board, slug, source in attempts:
        try:
            jobs = await fetch_board(fetcher, board, slug)
        except Exception as e:
            errors.append(f"{board}: {e}")
            continue
        if jobs:
            return summarize(board, slug, source, jobs)
    if errors:
        raise JobBoardsUnavailableError("; ".join(dict.fromkeys(errors)))
    return None
