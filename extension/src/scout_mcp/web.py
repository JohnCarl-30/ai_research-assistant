"""Web search and page reading.

Search uses the first configured provider: Brave Search, then Firecrawl, then
DuckDuckGo's HTML endpoint. DuckDuckGo needs no key but is best-effort: it is
unofficial, and it answers queries it takes for a bot with a CAPTCHA page.

Page reading uses Firecrawl when configured, since it renders JavaScript, and
plain HTTP plus HTML-to-text otherwise.

Every fetch is restricted to public http(s) addresses. The model decides what
to fetch, and the pages it reads can try to steer it, so without this a page
could have it read a router admin page or a cloud metadata endpoint on the
user's network.
"""

import asyncio
import ipaddress
import socket
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; ScoutResearch/0.1)"
MAX_PAGE_BYTES = 5_000_000


class BlockedURLError(ValueError):
    """The URL is not a public http(s) address."""


class SearchBlockedError(RuntimeError):
    """The search provider refused an automated query (e.g. a CAPTCHA page)."""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Page:
    url: str
    title: str
    text: str
    truncated: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def ensure_public_url(url: str) -> None:
    """Raise BlockedURLError unless every address the host resolves to is public."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BlockedURLError(f"Only http(s) URLs can be read: {url}")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as e:
        raise BlockedURLError(f"Cannot resolve {parsed.hostname}: {e}") from e
    if not infos or not all(_is_public_ip(info[4][0]) for info in infos):
        raise BlockedURLError(f"{parsed.hostname} is not a public address")


async def _check_request(request: httpx.Request) -> None:
    # Runs for every request the client sends, redirects included.
    await ensure_public_url(str(request.url))


def public_client(**kwargs) -> httpx.AsyncClient:
    """An httpx client that refuses non-public destinations, on every hop."""
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(20),
        event_hooks={"request": [_check_request]},
        **kwargs,
    )


# --- Search -------------------------------------------------------------------


async def brave_search(query: str, limit: int, api_key: str) -> list[SearchResult]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(limit, 20)},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        )
        r.raise_for_status()
    results = (r.json().get("web") or {}).get("results") or []
    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=BeautifulSoup(item.get("description", ""), "html.parser").get_text(),
        )
        for item in results[:limit]
    ]


async def firecrawl_search(query: str, limit: int, api_key: str) -> list[SearchResult]:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.firecrawl.dev/v2/search",
            json={"query": query, "limit": limit},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
    data = r.json().get("data") or {}
    # v2 groups results by source; tolerate the v1 flat list too.
    items = data.get("web", []) if isinstance(data, dict) else data
    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("description") or item.get("snippet") or "",
        )
        for item in items[:limit]
    ]


def parse_duckduckgo_html(html: str, limit: int) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for block in soup.select(".result"):
        link = block.select_one("a.result__a")
        if not link or not link.get("href"):
            continue
        href = link["href"]
        # Result links go through a redirector: //duckduckgo.com/l/?uddg=<target>
        target = parse_qs(urlparse(href).query).get("uddg", [href])[0]
        if "duckduckgo.com/y.js" in target:  # ads
            continue
        snippet = block.select_one(".result__snippet")
        results.append(
            SearchResult(
                title=link.get_text(strip=True),
                url=target,
                snippet=snippet.get_text(" ", strip=True) if snippet else "",
            )
        )
        if len(results) >= limit:
            break
    return results


def is_duckduckgo_challenge(status_code: int, html: str) -> bool:
    # DuckDuckGo answers suspected bots with HTTP 202 and an image CAPTCHA
    # ("anomaly") page. It looks like an empty result page, so it must be
    # detected rather than reported as "no results".
    return status_code == 202 or "anomaly-modal" in html


async def duckduckgo_search(query: str, limit: int) -> list[SearchResult]:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}) as client:
        r = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
        r.raise_for_status()
    if is_duckduckgo_challenge(r.status_code, r.text):
        raise SearchBlockedError("DuckDuckGo asked for a CAPTCHA, so the search was blocked")
    return parse_duckduckgo_html(r.text, limit)


async def search(
    query: str,
    limit: int = 8,
    *,
    brave_api_key: str | None = None,
    firecrawl_api_key: str | None = None,
) -> tuple[str, list[SearchResult]]:
    """Search the web with the best configured provider. Returns (provider, results)."""
    limit = max(1, min(limit, 20))
    if brave_api_key:
        return "brave", await brave_search(query, limit, brave_api_key)
    if firecrawl_api_key:
        return "firecrawl", await firecrawl_search(query, limit, firecrawl_api_key)
    return "duckduckgo", await duckduckgo_search(query, limit)


# --- Reading ------------------------------------------------------------------


def html_to_text(html: str) -> tuple[str, str]:
    """(title, readable text) of an HTML document."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines = (line.strip() for line in root.get_text("\n").splitlines())
    return title, "\n".join(line for line in lines if line)


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


async def _read_direct(url: str, max_chars: int) -> Page:
    async with public_client() as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            if not any(t in content_type for t in ("html", "text", "json", "xml")):
                raise ValueError(f"Not a text page ({content_type or 'unknown type'}): {url}")
            body = bytearray()
            async for chunk in r.aiter_bytes():
                body += chunk
                if len(body) > MAX_PAGE_BYTES:
                    break
            final_url = str(r.url)
            raw = body.decode(r.encoding or "utf-8", errors="replace")

    if "html" in content_type:
        title, text = html_to_text(raw)
    else:
        title, text = "", raw
    text, truncated = _truncate(text, max_chars)
    return Page(url=final_url, title=title, text=text, truncated=truncated)


async def _read_firecrawl(url: str, max_chars: int, api_key: str) -> Page:
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            "https://api.firecrawl.dev/v2/scrape",
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
    data = r.json().get("data") or {}
    metadata = data.get("metadata") or {}
    text, truncated = _truncate(data.get("markdown") or "", max_chars)
    return Page(
        url=metadata.get("sourceURL") or url,
        title=metadata.get("title") or "",
        text=text,
        truncated=truncated,
    )


async def read_page(
    url: str, max_chars: int = 20_000, *, firecrawl_api_key: str | None = None
) -> Page:
    """Readable text of a public web page."""
    await ensure_public_url(url)
    max_chars = max(500, min(max_chars, 100_000))
    if firecrawl_api_key:
        try:
            return await _read_firecrawl(url, max_chars, firecrawl_api_key)
        except httpx.HTTPError:
            pass  # fall back to a direct fetch
    return await _read_direct(url, max_chars)
