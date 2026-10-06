"""One-call company dossier: website, news, engineering, GitHub and saved notes.

Claude does the reasoning; this module does the legwork in one tool call so
the model starts from a complete, cited picture rather than issuing a dozen
searches itself. Each source is gathered independently and a failure in one
is reported in ``gaps`` rather than failing the dossier.

It also resolves the company's own domain from search results when the user
did not give one. The domain is what lets GitHub research confirm an org
belongs to the company (``high`` confidence) instead of guessing by name.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field

from scout_mcp.github import ToolCaller, _domain_root, candidate_org_slugs, research_github
from scout_mcp.notes import Notebook
from scout_mcp.web import Page, SearchResult

logger = logging.getLogger(__name__)

SearchFn = Callable[[str, int], Awaitable[list[SearchResult]]]
ReadFn = Callable[[str, int], Awaitable[Page]]
GitHubOpener = Callable[[], AbstractAsyncContextManager[ToolCaller | None]]

# (key, query template, results). Each angle answers a question a job seeker
# or analyst asks first.
ANGLES = [
    ("overview", "{company} company", 6),
    ("news", "{company} funding OR acquisition OR layoffs OR launch news", 6),
    ("engineering", "{company} engineering blog tech stack", 5),
    ("culture", "{company} careers culture reviews", 5),
]

# Hosts that are never a company's own site.
_AGGREGATORS = {
    "linkedin.com", "wikipedia.org", "crunchbase.com", "glassdoor.com", "indeed.com",
    "bloomberg.com", "reuters.com", "techcrunch.com", "youtube.com", "x.com",
    "twitter.com", "facebook.com", "instagram.com", "github.com", "medium.com",
    "reddit.com", "ycombinator.com", "pitchbook.com", "zoominfo.com", "forbes.com",
}

HOMEPAGE_CHARS = 4_000


@dataclass
class Dossier:
    company: str
    domain: str | None = None
    domain_source: str | None = None  # "given" or "search"
    homepage: dict | None = None
    sources: dict[str, list[dict]] = field(default_factory=dict)
    github: dict | None = None
    saved_notes: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "domain": self.domain,
            "domain_source": self.domain_source,
            "homepage": self.homepage,
            "sources": self.sources,
            "github": self.github,
            "saved_notes": self.saved_notes,
            "gaps": self.gaps,
        }


def _host(url: str) -> str:
    return _domain_root(url) or ""


def guess_domain(company: str, results: list[SearchResult]) -> str | None:
    """The company's own domain among search results, if one is recognisable.

    A result counts when a label of its host matches a slug of the company name:
    "Acme Robotics" matches acmerobotics.com and careers.acme-robotics.io (giving
    acme-robotics.io), but not acme.ai, which could be anyone.
    """
    slugs = set(candidate_org_slugs(company))
    for result in results:
        host = _host(result.url)
        if not host or any(host == a or host.endswith(f".{a}") for a in _AGGREGATORS):
            continue
        labels = host.split(".")
        for i, label in enumerate(labels[:-1]):
            if label in slugs:
                return ".".join(labels[i:])
    return None


async def research_company(
    company: str,
    *,
    domain: str | None,
    search: SearchFn,
    read: ReadFn,
    open_github: GitHubOpener | None,
    notebook: Notebook | None,
) -> Dossier:
    dossier = Dossier(company=company.strip())
    if domain:
        # Accepts "acme.io", "www.acme.io" or "https://acme.io/about".
        dossier.domain, dossier.domain_source = _domain_root(domain), "given"

    if notebook is not None:
        dossier.saved_notes = [
            {"id": n.id, "title": n.title, "url": n.url, "snippet": snip}
            for n, snip in notebook.search(company, limit=5)
        ]

    async def run_angle(key: str, template: str, limit: int) -> None:
        try:
            results = await search(template.format(company=dossier.company), limit)
            dossier.sources[key] = [r.to_dict() for r in results]
        except Exception as e:
            dossier.sources[key] = []
            dossier.gaps.append(f"{key} search failed: {e}")

    # Sequential: the keyless search fallback rate-limits parallel queries.
    for key, template, limit in ANGLES:
        await run_angle(key, template, limit)

    if not dossier.domain:
        overview = [SearchResult(**r) for r in dossier.sources.get("overview", [])]
        found = guess_domain(dossier.company, overview)
        if found:
            dossier.domain, dossier.domain_source = found, "search"
        else:
            dossier.gaps.append(
                "Could not identify the company's website; pass domain= to improve results."
            )

    async def read_homepage() -> None:
        if not dossier.domain:
            return
        try:
            page = await read(f"https://{dossier.domain}", HOMEPAGE_CHARS)
            dossier.homepage = page.to_dict()
        except Exception as e:
            dossier.gaps.append(f"Homepage could not be read: {e}")

    async def github() -> None:
        if open_github is None:
            dossier.gaps.append("GitHub research is off: no GitHub token configured.")
            return
        async with open_github() as call:
            if call is None:
                dossier.gaps.append("GitHub research unavailable: could not connect.")
                return
            try:
                profile = await research_github(dossier.company, call, domain=dossier.domain)
            except Exception as e:
                dossier.gaps.append(f"GitHub research failed: {e}")
                return
        if profile is None:
            dossier.gaps.append("No public GitHub organisation found.")
        else:
            dossier.github = profile.to_dict()

    await asyncio.gather(read_homepage(), github())
    return dossier
