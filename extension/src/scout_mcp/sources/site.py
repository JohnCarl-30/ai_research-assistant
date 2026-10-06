"""What a company's own website reveals: tech fingerprint, about text, links.

The homepage's HTML and headers show the frontend framework, hosting, CDN and
third-party services (analytics, support, payments), much as Wappalyzer does.
Its links are better than guesses: a link to github.com/<org> or to a job
board names the exact account, so later sources can skip slug guessing.
"""

import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scout_mcp.github import _domain_root
from scout_mcp.sources.http import DAY, Fetcher, Response
from scout_mcp.sources.jobs import Board, boards_linked

ABOUT_CHARS = 1500

# (label, category, where, pattern). "html" patterns search the raw HTML;
# "header" patterns search "name: value" header lines.
FINGERPRINTS: list[tuple[str, str, str, str]] = [
    ("Next.js", "framework", "html", r"/_next/static/|__NEXT_DATA__"),
    ("Nuxt", "framework", "html", r"__NUXT__|/_nuxt/"),
    ("Remix", "framework", "html", r"__remixContext"),
    ("Gatsby", "framework", "html", r"___gatsby"),
    ("Astro", "framework", "html", r"<astro-island|/_astro/"),
    ("SvelteKit", "framework", "html", r"__sveltekit|/_app/immutable/"),
    ("Angular", "framework", "html", r"ng-version="),
    ("WordPress", "cms", "html", r"/wp-content/|/wp-includes/"),
    ("Webflow", "cms", "html", r"data-wf-site|assets\.website-files\.com"),
    ("Framer", "cms", "html", r"framerusercontent\.com|framer\.com/m/"),
    ("Contentful", "cms", "html", r"ctfassets\.net"),
    ("Sanity", "cms", "html", r"cdn\.sanity\.io"),
    ("Shopify", "commerce", "html", r"cdn\.shopify\.com"),
    ("Vercel", "hosting", "header", r"^server: vercel|^x-vercel-id:"),
    ("Netlify", "hosting", "header", r"^server: netlify|^x-nf-request-id:"),
    ("Cloudflare", "cdn", "header", r"^server: cloudflare|^cf-ray:"),
    ("Amazon CloudFront", "cdn", "header", r"^x-amz-cf-id:|^via: .*cloudfront"),
    ("Fastly", "cdn", "header", r"^x-served-by: cache-|^fastly-"),
    ("Akamai", "cdn", "header", r"^x-akamai|^server: akamai"),
    ("Google Tag Manager", "analytics", "html", r"googletagmanager\.com"),
    ("Segment", "analytics", "html", r"cdn\.segment\.com"),
    ("Amplitude", "analytics", "html", r"cdn\.amplitude\.com|amplitude\.com/libs"),
    ("Mixpanel", "analytics", "html", r"cdn\.mxpnl\.com"),
    ("PostHog", "analytics", "html", r"posthog"),
    ("Hotjar", "analytics", "html", r"static\.hotjar\.com"),
    ("HubSpot", "marketing", "html", r"js\.hs-scripts\.com|js\.hsforms\.net"),
    ("Marketo", "marketing", "html", r"munchkin\.marketo\.net"),
    ("Intercom", "support", "html", r"widget\.intercom\.io|js\.intercomcdn\.com"),
    ("Zendesk", "support", "html", r"static\.zdassets\.com"),
    ("Drift", "support", "html", r"js\.driftt\.com"),
    ("Stripe", "payments", "html", r"js\.stripe\.com"),
    ("Sentry", "monitoring", "html", r"browser\.sentry-cdn\.com|sentry\.io/api"),
    ("Datadog", "monitoring", "html", r"datadoghq-browser-agent|browser-intake-datadoghq"),
    ("OneTrust", "consent", "html", r"cdn\.cookielaw\.org|optanon"),
]
_FINGERPRINTS = [
    (label, category, where, re.compile(pattern, re.I | re.M))
    for label, category, where, pattern in FINGERPRINTS
]

_GITHUB_ORG = re.compile(r"github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?=[/\"'?#\s]|$)")
_NOT_ORGS = {"about", "features", "pricing", "login", "join", "orgs", "sponsors", "topics",
             "marketplace", "site", "apps", "settings", "enterprise", "security", "collections"}
_CAREERS_TEXT = re.compile(r"\b(careers?|jobs|join us|we'?re hiring|open roles)\b", re.I)


@dataclass
class SiteInfo:
    url: str
    title: str | None = None
    description: str | None = None
    about: str | None = None
    tech: dict[str, list[str]] = field(default_factory=dict)
    github_orgs: list[str] = field(default_factory=list)
    job_boards: list[tuple[Board, str]] = field(default_factory=list)
    careers_url: str | None = None
    feeds: list[str] = field(default_factory=list)
    social: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def fingerprint(html_text: str, headers: dict[str, str]) -> dict[str, list[str]]:
    header_lines = "\n".join(f"{k.lower()}: {v.lower()}" for k, v in headers.items())
    found: dict[str, list[str]] = {}
    for label, category, where, rx in _FINGERPRINTS:
        if rx.search(html_text if where == "html" else header_lines):
            found.setdefault(category, []).append(label)
    return found


def github_orgs(html_text: str) -> list[str]:
    orgs: list[str] = []
    for org in _GITHUB_ORG.findall(html_text):
        if org.lower() not in _NOT_ORGS and org.lower() not in (o.lower() for o in orgs):
            orgs.append(org)
    return orgs


def _same_site(url: str, domain: str) -> bool:
    host = _domain_root(url) or ""
    return host == domain or host.endswith(f".{domain}")


def parse_page(page: Response, domain: str) -> SiteInfo:
    soup = BeautifulSoup(page.text, "html.parser")
    info = SiteInfo(url=page.url)
    info.title = soup.title.get_text(strip=True) if soup.title else None
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    info.description = meta.get("content") if meta else None
    info.tech = fingerprint(page.text, page.headers)
    info.github_orgs = github_orgs(page.text)
    info.job_boards = boards_linked(page.text)

    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel") or [])
        if "alternate" in rel and "xml" in (link.get("type") or ""):
            info.feeds.append(urljoin(page.url, link["href"]))

    for a in soup.find_all("a", href=True):
        href = urljoin(page.url, a["href"])
        host = urlparse(href).hostname or ""
        if any(s in host for s in ("linkedin.com", "x.com", "twitter.com", "youtube.com")):
            if href not in info.social:
                info.social.append(href)
        if info.careers_url is None and _CAREERS_TEXT.search(a.get_text(" ", strip=True)):
            info.careers_url = href

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    text = " ".join(root.get_text(" ", strip=True).split())
    info.about = text[:ABOUT_CHARS] or None
    info.social = info.social[:6]
    return info


async def inspect(fetcher: Fetcher, domain: str) -> SiteInfo:
    """The homepage, plus the careers page when it links to one (for job boards)."""
    home = await fetcher.get(f"https://{domain}/", ttl=DAY)
    info = parse_page(home, domain)

    if info.careers_url and not info.job_boards:
        careers_url = info.careers_url
        try:
            if _same_site(careers_url, domain):
                careers = await fetcher.get(careers_url, ttl=DAY)
                info.job_boards = boards_linked(careers.text)
                for org in github_orgs(careers.text):
                    if org not in info.github_orgs:
                        info.github_orgs.append(org)
            else:
                # A careers link that points straight at a job board.
                info.job_boards = boards_linked(careers_url)
        except Exception:
            pass  # the homepage findings stand on their own
    return info
