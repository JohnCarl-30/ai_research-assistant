"""Hacker News stories that link to the company's website.

Searching HN by company name is noisy ("Linear" finds linear algebra), so
stories are matched by the URL they link to instead: launches, engineering
posts and announcements published on the company's own domain.
"""

from urllib.parse import urlencode

from scout_mcp.github import _domain_root
from scout_mcp.sources.http import HOUR, Fetcher

API = "https://hn.algolia.com/api/v1/{endpoint}"
FIELDS = "title,url,points,num_comments,created_at,objectID"


def _story(hit: dict) -> dict:
    return {
        "title": hit.get("title"),
        "url": hit.get("url"),
        "points": hit.get("points") or 0,
        "comments": hit.get("num_comments") or 0,
        "date": (hit.get("created_at") or "")[:10],
        "discussion": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
    }


def _on_domain(hit: dict, domain: str) -> bool:
    host = _domain_root(hit.get("url")) or ""
    return host == domain or host.endswith(f".{domain}")


async def stories(fetcher: Fetcher, domain: str) -> dict:
    """Top stories of all time and the most recent ones, linking to the domain."""
    params = {
        "query": domain, "restrictSearchableAttributes": "url", "tags": "story",
        "hitsPerPage": 30, "attributesToRetrieve": FIELDS,
    }
    top = await fetcher.get_json(API.format(endpoint="search") + "?" + urlencode(params),
                                 ttl=6 * HOUR)
    recent = await fetcher.get_json(
        API.format(endpoint="search_by_date") + "?" + urlencode(params), ttl=6 * HOUR
    )
    top_hits = [h for h in top.get("hits", []) if _on_domain(h, domain)]
    recent_hits = [h for h in recent.get("hits", []) if _on_domain(h, domain)]
    latest = max((h.get("created_at") or "" for h in recent_hits), default="")
    return {
        "top": [_story(h) for h in top_hits[:6]],
        "recent": [_story(h) for h in recent_hits[:6]],
        "last_story": latest[:10] or None,
    }
