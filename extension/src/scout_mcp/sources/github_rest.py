"""GitHub research without a token, over GitHub's public REST API.

``research_github`` talks to a ToolCaller that speaks the GitHub MCP server's
two read-only tools. This adapter answers the same two calls from the REST
API, which returns the same JSON, so the research logic is shared.

Without a token GitHub allows 60 requests an hour (search: 10 a minute) per
IP. One company costs about ten, so responses are cached for a day and a
rate-limit answer is raised as its own error instead of reading as "no org".
An optional GITHUB_TOKEN raises the limit to 5,000 an hour.
"""

import json
from urllib.parse import quote, urlencode

from scout_mcp.github import ALLOWED_TOOLS, GitHubToolError, ToolCaller
from scout_mcp.sources.http import DAY, Fetcher, FetchError

API = "https://api.github.com"


class GitHubRateLimitError(RuntimeError):
    """GitHub's unauthenticated rate limit is used up for now."""


class GitHubUnavailableError(RuntimeError):
    """GitHub failed (server error, network), as opposed to "no such org"."""


def _headers(token: str | None, accept: str = "application/vnd.github+json") -> dict:
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_rest_caller(fetcher: Fetcher, token: str | None = None) -> ToolCaller:
    async def get(url: str, accept: str = "application/vnd.github+json") -> str:
        try:
            return (await fetcher.get(url, ttl=DAY, headers=_headers(token, accept))).text
        except FetchError as e:
            if e.status in (403, 429) and "rate limit" in str(e).lower():
                raise GitHubRateLimitError(
                    "GitHub's limit for requests without a token is used up "
                    "(60 an hour); try again later."
                ) from e
            if e.status in (404, 422):
                # Not found, or a search on an org that doesn't exist: "not this one".
                raise GitHubToolError(str(e)) from e
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
            return await get(f"{API}/search/repositories?{urlencode(params)}")

        owner, repo = quote(args["owner"]), quote(args["repo"])
        path = args.get("path", "/").strip("/")
        if not path:
            listing = json.loads(await get(f"{API}/repos/{owner}/{repo}/contents/"))
            fields = args.get("fields") or ["name", "type"]
            return json.dumps([{k: e.get(k) for k in fields} for e in listing])
        return await get(
            f"{API}/repos/{owner}/{repo}/contents/{quote(path)}",
            accept="application/vnd.github.raw+json",
        )

    return call
