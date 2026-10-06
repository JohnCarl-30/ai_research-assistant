"""One-call company dossier from keyless public sources.

Order matters, because each step makes the next more exact:

1. Wikidata settles identity: the official website (so the domain) and often
   the exact GitHub org. A name-only match is accepted only if unambiguous.
2. With the domain: the website (tech fingerprint, about text, and links to
   the exact GitHub org and job board), DNS (email and SaaS tools) and Hacker
   News stories linking to the site, in parallel.
3. Then hiring (job boards) and GitHub, preferring the exact accounts found in
   steps 1-2 over name guesses.

There is deliberately no web search here: Claude has its own, and keyless
search scraping is fragile. Every source fails on its own into ``gaps``.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from scout_mcp.github import _domain_root, candidate_org_slugs, research_github
from scout_mcp.notes import Notebook
from scout_mcp.sources import dnsinfo, hn, jobs, site, wikidata
from scout_mcp.sources.github_rest import (
    GitHubRateLimitError,
    find_org_by_website,
    github_rest_caller,
)
from scout_mcp.sources.http import Fetcher

DnsLookup = Callable[[str], Awaitable[dnsinfo.DnsInfo]]
Progress = Callable[[int, str], Awaitable[None]]  # (step 1-3, what's happening)

WEB_SEARCH_STEP = (
    "This dossier covers structured public sources only. Use your own web search "
    "for recent news, funding rounds and employee reviews."
)


@dataclass
class Dossier:
    company: str
    domain: str | None = None
    domain_source: str | None = None  # "given" or "wikidata"
    facts: dict | None = None
    website: dict | None = None
    dns: dict | None = None
    hiring: dict | None = None
    github: dict | None = None
    hacker_news: dict | None = None
    saved_notes: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _pick_org(orgs: list[str], company: str, domain: str | None) -> str | None:
    """The site's GitHub link most like the company, if it links to any."""
    if not orgs:
        return None
    slugs = set(candidate_org_slugs(company, domain))
    return next((o for o in orgs if o.lower() in slugs), orgs[0])


async def research_company(
    company: str,
    *,
    domain: str | None,
    fetcher: Fetcher,
    notebook: Notebook | None,
    github_token: str | None = None,
    dns_lookup: DnsLookup | None = None,
    progress: Progress | None = None,
) -> Dossier:
    dns_lookup = dns_lookup or dnsinfo.lookup

    async def report(step: int, message: str) -> None:
        if progress is not None:
            await progress(step, message)

    d = Dossier(company=company.strip())
    if domain:
        d.domain, d.domain_source = _domain_root(domain), "given"

    if notebook is not None:
        d.saved_notes = [
            {"id": n.id, "title": n.title, "url": n.url, "snippet": snip}
            for n, snip in notebook.search(d.company, limit=5)
        ]

    # 1. Identity.
    await report(1, "Looking the company up on Wikidata")
    facts = None
    try:
        found = await wikidata.lookup(fetcher, d.company, d.domain)
        facts = found.facts
        if facts:
            d.facts = facts.to_dict()
            if not d.domain and facts.website:
                d.domain, d.domain_source = _domain_root(facts.website), "wikidata"
        elif found.ambiguous:
            d.gaps.append(
                f"Several companies are named {d.company!r} on Wikidata "
                f"({'; '.join(found.ambiguous)}); pass domain= to pick one."
            )
        else:
            d.gaps.append("No Wikidata entry matched this company.")
    except Exception as e:
        d.gaps.append(f"Wikidata lookup failed: {e}")

    if not d.domain:
        d.gaps.append("Website unknown, so website, DNS and Hacker News checks were skipped.")
        d.next_steps.append(
            "Find the company's official website with your web search, then call "
            "research_company again with domain= for a much fuller dossier."
        )

    # 2. The company's own web presence.
    site_info = None

    async def get_site() -> None:
        nonlocal site_info
        try:
            site_info = await site.inspect(fetcher, d.domain)
            d.website = site_info.to_dict()
        except Exception as e:
            d.gaps.append(f"Website could not be read: {e}")

    async def get_dns() -> None:
        try:
            d.dns = (await dns_lookup(d.domain)).to_dict()
        except Exception as e:
            d.gaps.append(f"DNS lookup failed: {e}")

    async def get_hn() -> None:
        try:
            d.hacker_news = await hn.stories(fetcher, d.domain)
        except Exception as e:
            d.gaps.append(f"Hacker News search failed: {e}")

    if d.domain:
        await report(2, "Reading the website, DNS and Hacker News")
        await asyncio.gather(get_site(), get_dns(), get_hn())

    # A site that redirects to a subdomain (gitlab.com -> about.gitlab.com) is
    # often on Wikidata under that host. Only subdomains: a redirect to another
    # domain (an acquirer, say) would bring in a different company's facts.
    if facts is None and site_info is not None:
        final = _domain_root(site_info.url)
        if final and final != d.domain and final.endswith(f".{d.domain}"):
            try:
                facts = (await wikidata.lookup(fetcher, d.company, final)).facts
            except Exception:
                facts = None  # the first lookup's gap already says what's missing
            if facts:
                d.facts = facts.to_dict()
                d.gaps = [g for g in d.gaps if not g.startswith("No Wikidata entry")]

    # 3. Hiring and engineering, from exact accounts where known.
    async def get_hiring() -> None:
        linked = site_info.job_boards if site_info else []
        try:
            hiring = await jobs.find_hiring(
                fetcher, linked, candidate_org_slugs(d.company, d.domain)
            )
        except Exception as e:
            d.gaps.append(f"Job board lookup failed: {e}")
            return
        if hiring is None:
            d.gaps.append(
                "No public job board found (checked Greenhouse, Lever, Ashby, Workable, "
                "SmartRecruiters, Recruitee and Personio)."
            )
        else:
            d.hiring = hiring.to_dict()

    async def get_github() -> None:
        org = facts.github if facts and facts.github else None
        source = "wikidata" if org else None
        if not org and site_info:
            org = _pick_org(site_info.github_orgs, d.company, d.domain)
            source = "website" if org else None
        call = github_rest_caller(fetcher, github_token)
        try:
            profile = await research_github(d.company, call, domain=d.domain, org=org)
            if (profile is None or profile.confidence == "low") and not org and d.domain:
                # Last resort: an org whose GitHub profile lists the company's site.
                listed = await find_org_by_website(fetcher, d.company, d.domain, github_token)
                if listed:
                    profile = await research_github(d.company, call, domain=d.domain, org=listed)
                    source = "github profile"
        except GitHubRateLimitError as e:
            d.gaps.append(str(e))
            return
        except Exception as e:
            d.gaps.append(f"GitHub research failed: {e}")
            return
        if profile is None:
            d.gaps.append("No public GitHub organisation found.")
        else:
            d.github = {**profile.to_dict(), "org_source": source or "guess"}

    await report(3, "Checking job boards and GitHub")
    await asyncio.gather(get_hiring(), get_github())
    d.next_steps.append(WEB_SEARCH_STEP)
    return d
