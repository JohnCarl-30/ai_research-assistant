"""Reading public web pages, and the guard that keeps every fetch public.

Every fetch is restricted to public http(s) addresses. The model decides what
to fetch, and the pages it reads can try to steer it, so without this a page
could have it read a router admin page or a cloud metadata endpoint on the
user's network.
"""

import asyncio
import ipaddress
import socket
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; ScoutResearch/0.1)"
MAX_PAGE_BYTES = 5_000_000


class BlockedURLError(ValueError):
    """The URL is not a public http(s) address."""


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


def public_client(timeout: float = 20, **kwargs) -> httpx.AsyncClient:
    """An httpx client that refuses non-public destinations, on every hop."""
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(timeout),
        event_hooks={"request": [_check_request]},
        **kwargs,
    )


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


async def read_page(url: str, max_chars: int = 20_000) -> Page:
    """Readable text of a public web page."""
    await ensure_public_url(url)
    max_chars = max(500, min(max_chars, 100_000))
    return await _read_direct(url, max_chars)
