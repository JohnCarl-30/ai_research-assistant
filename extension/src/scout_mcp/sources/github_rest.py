"""GitHub research without a token: the search API plus raw file downloads.

``research_github`` talks to a ToolCaller that speaks the GitHub MCP server's
two read-only tools. This adapter answers the same two calls without spending
GitHub's tiny keyless API quota (60 requests an hour):

- ``search_repositories`` uses the search API, which has its own separate
  allowance (10 requests a minute without a token).
- ``get_file_contents`` reads from raw.githubusercontent.com, which is not
  counted against the API quota. A root listing is answered by checking which
  of the dependency manifests research reads exist there, so the core API is
  not used at all.

Responses are cached for a day. When the search limit (10 a minute) is used
up and frees up within a minute, the request waits for it and is tried once
more; otherwise a rate-limit answer is raised as its own error instead of
reading as "no org". An optional token raises the
search allowance to 30 a minute.
"""

import asyncio
import json
import time
from urllib.parse import quote, urlencode

from scout_mcp.github import ALLOWED_TOOLS, MANIFESTS, GitHubToolError, ToolCaller, _domain_root
from scout_mcp.sources.http import DAY, Fetcher, FetchError

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


# The longest Scout waits for GitHub's rate limit to reset before giving up
# and reporting it. The search limit resets every minute; the hourly core
# limit is never worth waiting for.
MAX_RATE_LIMIT_WAIT = 60

# Indirections so tests don't really wait.
_sleep = asyncio.sleep
_now = time.time


class GitHubRateLimitError(RuntimeError):
    """GitHub's rate limit for requests without a token is used up for now."""


class GitHubUnavailableError(RuntimeError):
    """GitHub failed (server error, network), as opposed to "no such org"."""


def _headers(token: str | None) -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _rate_limit_message(url: str) -> str:
    if "/search/" in url:
        return ("GitHub's search limit for requests without a token is used up "
                "(10 a minute); try again in a minute.")
    return ("GitHub's limit for requests without a token is used up "
            "(60 an hour); try again later.")


def _rate_limit_wait(e: FetchError) -> float | None:
    """Seconds until GitHub's limit frees up, if it says and it's soon."""
    try:
        if "retry-after" in e.headers:
            wait = float(e.headers["retry-after"])
        elif "x-ratelimit-reset" in e.headers:
            wait = float(e.headers["x-ratelimit-reset"]) - _now()
        else:
            return None
    except ValueError:
        return None
    return max(wait, 0.0) if wait <= MAX_RATE_LIMIT_WAIT else None


async def _api(fetcher: Fetcher, url: str, token: str | None, retry: bool = True) -> str:
    try:
        return (await fetcher.get(url, ttl=DAY, headers=_headers(token))).text
    except FetchError as e:
        if e.status in (403, 429) and "rate limit" in str(e).lower():
            wait = _rate_limit_wait(e) if retry else None
            if wait is None:
                raise GitHubRateLimitError(_rate_limit_message(url)) from e
            await _sleep(wait + 1)
            return await _api(fetcher, url, token, retry=False)
        if e.status in (404, 422):
            # Not found, or a search on an org that doesn't exist: "not this one".
            raise GitHubToolError(str(e)) from e
        raise GitHubUnavailableError(str(e)) from e


async def find_org_by_website(
    fetcher: Fetcher, company: str, domain: str, token: str | None = None, checks: int = 3
) -> str | None:
    """The GitHub org whose profile website is the company's domain, if any.

    For companies whose org name can't be guessed and isn't linked from their
    site (GitLab's is "gitlabhq"). Costs one search plus up to ``checks``
    profile reads, so it is only worth calling when the cheaper ways failed.
    A match is GitHub's own record of the org's website, so it is trusted.
    """
    params = urlencode({"q": f"{company} type:org", "per_page": 5})
    found = json.loads(await _api(fetcher, f"{API}/search/users?{params}", token))
    for item in found.get("items", [])[:checks]:
        login = item.get("login")
        if not login:
            continue
        try:
            profile = json.loads(await _api(fetcher, f"{API}/orgs/{quote(login)}", token))
        except GitHubToolError:
            continue
        site = _domain_root(profile.get("blog") or "")
        if site and (site == domain or site.endswith(f".{domain}")):
            return login
    return None


def site_name(site: str | None) -> str | None:
    """The name a website is registered under: "careers.doctolib.com" and
    "www.doctolib.fr" are both "doctolib"; "shop.acme.co.uk" is "acme"."""
    host = _domain_root(site or "")
    if not host:
        return None
    labels = host.split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and len(labels[-2]) <= 3:
        return labels[-3]  # acme.co.uk, acme.com.au
    return labels[-2] if len(labels) >= 2 else None


async def org_website(
    fetcher: Fetcher, login: str, token: str | None = None
) -> str | None:
    """The website on a GitHub org's profile ("" if it lists none). One core
    API call."""
    profile = json.loads(await _api(fetcher, f"{API}/orgs/{quote(login)}", token))
    return profile.get("blog") or ""


def github_rest_caller(fetcher: Fetcher, token: str | None = None) -> ToolCaller:
    # Default branches seen in search results, so raw URLs name the right one.
    branches: dict[str, str] = {}

    async def api(url: str) -> str:
        return await _api(fetcher, url, token)

    async def raw(owner: str, repo: str, path: str) -> str | None:
        """A file's text, or None if the repository has no such file."""
        branch = branches.get(f"{owner}/{repo}".lower(), "HEAD")
        url = f"{RAW}/{quote(owner)}/{quote(repo)}/{quote(branch)}/{quote(path)}"
        try:
            return (await fetcher.get(url, ttl=DAY)).text
        except FetchError as e:
            if e.status == 404:
                return None
            raise GitHubUnavailableError(str(e)) from e

    async def call(tool: str, args: dict) -> str:
        if tool not in ALLOWED_TOOLS:
            raise PermissionError(f"GitHub tool {tool!r} is not allowed")

        if tool == "search_repositories":
            params = {
                "q": args["query"],
                "sort": args.get("sort", "stars"),
                "order": args.get("order", "desc"),
                "per_page": args.get("perPage", 10),
            }
            text = await api(f"{API}/search/repositories?{urlencode(params)}")
            for item in json.loads(text).get("items", []):
                if item.get("full_name") and item.get("default_branch"):
                    branches[item["full_name"].lower()] = item["default_branch"]
            return text

        owner, repo = args["owner"], args["repo"]
        path = args.get("path", "/").strip("/")
        if not path:
            # Which of the manifests research reads exist, without the core API.
            names = list(MANIFESTS)
            found = await asyncio.gather(*(raw(owner, repo, name) for name in names))
            return json.dumps(
                [{"name": n, "type": "file"} for n, text in zip(names, found) if text is not None]
            )
        text = await raw(owner, repo, path)
        if text is None:
            raise GitHubToolError(f"{owner}/{repo} has no {path}")
        return text

    return call
