"""Hiring signals from public job boards.

Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee and Personio
all publish a company's open roles without a key (Personio as XML, the rest as
JSON). The board name is usually the company's slug; when the company's own
site links to its board, that exact name is used instead of a guess.

Job descriptions name the tools a team actually uses, so they are also a tech
stack source that does not depend on the company publishing code.
"""

import asyncio
import html
import re
import warnings
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Literal
from urllib.parse import urlparse

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from scout_mcp.sources.http import HOUR, Fetcher, FetchError
from scout_mcp.web import BlockedURLError

Board = Literal[
    "greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee", "personio"
]

BOARD_URLS: dict[Board, str] = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true",
    # Lists up to 100 postings without descriptions, plus the true total.
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
    "recruitee": "https://{slug}.recruitee.com/api/offers/",
    "personio": "https://{slug}.jobs.personio.de/xml",
}

# Boards whose name becomes part of the hostname: names are checked first.
_SUBDOMAIN_BOARDS = {"recruitee", "personio"}
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

# Links on a company's site that name its board exactly.
BOARD_LINKS: dict[Board, re.Pattern] = {
    "greenhouse": re.compile(
        r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)"
    ),
    "lever": re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"),
    "workable": re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)"),
    "smartrecruiters": re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    "recruitee": re.compile(r"([a-z0-9-]+)\.recruitee\.com"),
    "personio": re.compile(r"([a-z0-9-]+)\.jobs\.personio\.(?:de|com)"),
}
_NOT_BOARD_NAMES = {"embed", "api", "v1", "j", "www", "app", "careers", "jobs"}

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
    # When the board lists only part of its roles (SmartRecruiters: 100), the
    # breakdowns cover this many of the open_roles.
    roles_analysed: int | None = None
    # The employer the board names, on boards that name one.
    employer: str | None = None

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


def _place(*parts: str | None) -> str | None:
    return ", ".join(p for p in parts if p) or None


def parse_workable(data: dict) -> list[Job]:
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(Job(
            title=j.get("title", ""),
            department=j.get("department") or j.get("function"),
            location=_place(j.get("city"), j.get("country")),
            remote=bool(j.get("telecommuting")),
            url=j.get("url") or j.get("shortlink"),
            text=_plain(j.get("description")),
        ))
    return jobs


def parse_smartrecruiters(data: dict) -> list[Job]:
    jobs = []
    for j in data.get("content", []):
        location = j.get("location") or {}
        company = (j.get("company") or {}).get("identifier")
        jobs.append(Job(
            title=j.get("name", ""),
            department=(j.get("department") or {}).get("label")
            or (j.get("function") or {}).get("label"),
            location=location.get("fullLocation") or _place(location.get("city")),
            remote=bool(location.get("remote")),
            url=f"https://jobs.smartrecruiters.com/{company}/{j['id']}"
            if company and j.get("id") else None,
            text="",  # the listing has no descriptions
        ))
    return jobs


def parse_recruitee(data: dict) -> list[Job]:
    jobs = []
    for j in data.get("offers", []):
        if j.get("status", "published") != "published":
            continue
        jobs.append(Job(
            title=j.get("title", ""),
            department=j.get("department"),
            location=j.get("location") or _place(j.get("city"), j.get("country")),
            remote=bool(j.get("remote")),
            url=j.get("careers_url"),
            text=f"{_plain(j.get('description'))} {_plain(j.get('requirements'))}",
        ))
    return jobs


def parse_personio(xml_text: str, slug: str) -> list[Job]:
    # html.parser rather than an XML parser: it never expands entities, so a
    # hostile feed can't blow up memory (the "billion laughs" attack).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(xml_text, "html.parser")
    jobs = []
    for p in soup.find_all("position"):
        def text(tag: str) -> str | None:
            node = p.find(tag)
            return node.get_text(" ", strip=True) if node else None

        office = text("office")
        descriptions = " ".join(
            _plain(v.get_text()) for v in p.find_all("value")
        )
        jobs.append(Job(
            title=text("name") or "",
            department=text("department") or text("recruitingcategory"),
            location=office,
            remote="remote" in (office or "").lower(),
            url=f"https://{slug}.jobs.personio.de/job/{text('id')}" if text("id") else None,
            text=descriptions,
        ))
    return jobs


def _personio_employer(xml_text: str) -> str | None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        node = BeautifulSoup(xml_text, "html.parser").find("subcompany")
    return node.get_text(" ", strip=True) or None if node else None


PARSERS = {
    "greenhouse": parse_greenhouse, "lever": parse_lever, "ashby": parse_ashby,
    "workable": parse_workable, "smartrecruiters": parse_smartrecruiters,
    "recruitee": parse_recruitee,
}
BOARD_PAGES = {
    "greenhouse": "https://job-boards.greenhouse.io/{slug}",
    "lever": "https://jobs.lever.co/{slug}",
    "ashby": "https://jobs.ashbyhq.com/{slug}",
    "workable": "https://apply.workable.com/{slug}/",
    "smartrecruiters": "https://jobs.smartrecruiters.com/{slug}",
    "recruitee": "https://{slug}.recruitee.com/",
    "personio": "https://{slug}.jobs.personio.de/",
}


def tech_mentions(jobs: list[Job]) -> list[tuple[str, int]]:
    """How many roles mention each technology (a role counts once per term)."""
    counts: Counter = Counter()
    for job in jobs:
        counts.update({label for label, rx in _TECH if rx.search(job.text)})
    return counts.most_common(15)


def summarize(
    board: Board, slug: str, source: str, jobs: list[Job], total: int | None = None,
    employer: str | None = None,
) -> Hiring:
    partial = total is not None and total > len(jobs)
    return Hiring(
        board=board,
        slug=slug,
        board_source=source,
        open_roles=total if partial else len(jobs),
        roles_analysed=len(jobs) if partial else None,
        by_department=Counter(j.department or "Unspecified" for j in jobs).most_common(8),
        by_location=Counter(j.location or "Unspecified" for j in jobs).most_common(6),
        remote_share=round(sum(j.remote for j in jobs) / len(jobs), 2) if jobs else None,
        tech_mentions=tech_mentions(jobs),
        sample_roles=[
            {"title": j.title, "department": j.department, "location": j.location, "url": j.url}
            for j in jobs[:10]
        ],
        board_url=BOARD_PAGES[board].format(slug=slug),
        employer=employer,
    )


def boards_linked(html_text: str) -> list[tuple[Board, str]]:
    """Job boards a page links to, as (board, slug)."""
    found: list[tuple[Board, str]] = []
    for board, rx in BOARD_LINKS.items():
        for slug in rx.findall(html_text):
            if slug.lower() not in _NOT_BOARD_NAMES and (board, slug) not in found:
                found.append((board, slug))
    return found


# Full boards with descriptions run to megabytes for large employers (Stripe,
# Cloudflare and Palantir each passed 5 MB), so they get a higher limit, and
# the summary is cached rather than the raw board.
BOARD_MAX_BYTES = 40_000_000
BOARD_TTL = 6 * HOUR


def employer_of(board: Board, data: dict) -> str | None:
    """The employer a JSON board names, for the boards that name one."""
    if board == "workable":
        return data.get("name") or None
    if board == "smartrecruiters":
        first = next(iter(data.get("content") or []), {})
        return (first.get("company") or {}).get("name") or None
    if board == "recruitee":
        first = next(iter(data.get("offers") or []), {})
        return first.get("company_name") or None
    return None


_EMPLOYER_SUFFIXES = {"inc", "ltd", "llc", "gmbh", "ag", "se", "co", "kg", "bv", "sa", "sas",
                      "ab", "plc", "corp", "corporation", "company", "group", "the", "and"}


def same_employer(company: str, employer: str) -> bool:
    """Whether a board's employer name could be this company ("Personio SE &
    Co. KG" is Personio; "FD Sandbox" is not)."""
    def words(name: str) -> set[str]:
        found = set(re.findall(r"[a-z0-9]+", name.lower()))
        return (found - _EMPLOYER_SUFFIXES) or found

    a, b = words(company), words(employer)
    return bool(a & b) or "".join(sorted(a)) == "".join(sorted(b)) or (
        "".join(re.findall(r"[a-z0-9]+", company.lower()))
        in "".join(re.findall(r"[a-z0-9]+", employer.lower())))


async def fetch_board(
    fetcher: Fetcher, board: Board, slug: str
) -> tuple[list[Job], int | None, str | None] | None:
    """The board's jobs, its total count if it reports one and the employer
    it names, or None if this company has no such board."""
    if board in _SUBDOMAIN_BOARDS:
        slug = slug.lower()
        if not _HOST_LABEL.match(slug):
            return None
    url = BOARD_URLS[board].format(slug=slug)
    try:
        if board == "personio":
            response = await fetcher.get(
                url, ttl=BOARD_TTL, max_bytes=BOARD_MAX_BYTES, cache=False
            )
            if response.truncated:
                raise FetchError(url, 413, f"Response from {url} is too large to read")
            jobs, total = parse_personio(response.text, slug), None
            employer = _personio_employer(response.text)
        else:
            data = await fetcher.get_json(
                url, ttl=BOARD_TTL, max_bytes=BOARD_MAX_BYTES, cache=False
            )
            jobs = PARSERS[board](data)
            total = data.get("totalFound") if board == "smartrecruiters" else None
            employer = employer_of(board, data)
    except FetchError as e:
        if e.status in (404, 400, 410, 422):
            return None
        if urlparse(e.final_url).hostname != urlparse(url).hostname:
            # An unknown subdomain board redirects to the vendor's own site
            # (Personio's is rate limited): no such board, not an outage.
            return None
        raise
    except BlockedURLError:
        return None  # a subdomain board whose name doesn't resolve: no such board
    # Lever and SmartRecruiters answer unknown boards with an empty list.
    return (jobs, total, employer) if jobs else None


async def _hiring_on(fetcher: Fetcher, board: Board, slug: str, source: str) -> Hiring | None:
    """The board's hiring summary, from cache when fresh (including "no board")."""
    key = f"hiring {board} {slug}"
    cache = fetcher.cache
    if cache is not None and (hit := cache.get(key, BOARD_TTL)) is not None:
        return Hiring(**{**hit["hiring"], "board_source": source}) if hit["hiring"] else None
    found = await fetch_board(fetcher, board, slug)
    hiring = summarize(board, slug, source, *found) if found else None
    if cache is not None:
        cache.set(key, {"hiring": hiring.to_dict() if hiring else None})
    return hiring


async def find_hiring(
    fetcher: Fetcher, linked: list[tuple[Board, str]], guesses: list[str],
    company: str | None = None,
) -> Hiring | None:
    """Try boards the company's site links to first, then slug guesses.

    One board being down must not hide another, so each attempt fails on its
    own. Only when nothing was found and some attempts failed is that an
    error (the board may exist on a service that was unreachable).
    """
    errors: list[str] = []

    async def attempt(board: Board, slug: str, source: str) -> Hiring | None:
        try:
            return await _hiring_on(fetcher, board, slug, source)
        except Exception as e:
            errors.append(f"{board}: {e}")
            return None

    for board, slug in linked:
        if hiring := await attempt(board, slug, "website"):
            return hiring
    # Guesses: every board at once for each name, first board in order wins.
    for slug in guesses:
        boards = [b for b in BOARD_URLS if (b, slug) not in linked]
        results = await asyncio.gather(*(attempt(b, slug, "guess") for b in boards))
        # A guessed board that names a different employer is someone else's.
        results = [h for h in results if h and not (
            company and h.employer and not same_employer(company, h.employer))]
        if results:
            return results[0]
    if errors:
        raise JobBoardsUnavailableError("; ".join(dict.fromkeys(errors)))
    return None
