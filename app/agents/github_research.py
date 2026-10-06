"""Company research signals from GitHub, gathered through the GitHub MCP server.

A company's public GitHub organisation says more about its real tech stack than
an LLM's memory does: which languages its repos are written in, which
frameworks its manifests depend on, and whether it is still shipping. This
module finds the org and condenses that into a ``GitHubProfile`` the research
prompt can cite.

The gathering is deterministic (a fixed sequence of read-only tool calls, no
LLM in the loop) so it is cheap, repeatable and testable offline. Everything
talks to the server through a ``ToolCaller`` — ``(tool_name, args) -> text`` —
so tests substitute a fake and production uses ``github_mcp_caller``.
"""

import asyncio
import json
import logging
import re
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import asdict, dataclass, field
from typing import Literal
from urllib.parse import urlparse

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

ToolCaller = Callable[[str, dict], Awaitable[str]]

# Read-only tools this module may call. The server is also opened with the
# read-only header; this is the second lock on the same door.
ALLOWED_TOOLS = frozenset({"search_repositories", "get_file_contents"})

REPOS_SAMPLED = 10
REPOS_INSPECTED = 3

# Legal-form suffixes dropped when guessing an org login from a company name.
_COMPANY_SUFFIXES = {
    "inc", "llc", "ltd", "limited", "corp", "corporation", "co", "company",
    "gmbh", "plc", "sa", "ag", "bv", "pte", "pty",
}
_GITHUB_LOGIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$")

# Dependency name -> label, per manifest file. Labels match TECH_KEYWORDS
# spelling where one exists so tags and research agree.
_NPM_FRAMEWORKS = {
    "react": "react", "next": "next.js", "vue": "vue", "nuxt": "nuxt",
    "@angular/core": "angular", "svelte": "svelte", "express": "express",
    "@nestjs/core": "nestjs", "graphql": "graphql", "typescript": "typescript",
    "tailwindcss": "tailwind",
}
_PYTHON_FRAMEWORKS = {
    "django": "django", "flask": "flask", "fastapi": "fastapi", "torch": "pytorch",
    "tensorflow": "tensorflow", "langchain": "langchain", "sqlalchemy": "sqlalchemy",
    "celery": "celery", "pandas": "pandas",
}
_GO_FRAMEWORKS = {
    "github.com/gin-gonic/gin": "gin", "github.com/gofiber/fiber": "fiber",
    "google.golang.org/grpc": "grpc", "github.com/labstack/echo": "echo",
}
_RUST_FRAMEWORKS = {"tokio": "tokio", "actix-web": "actix", "axum": "axum"}
_RUBY_FRAMEWORKS = {"rails": "rails", "sinatra": "sinatra"}

MANIFESTS: dict[str, dict[str, str]] = {
    "package.json": _NPM_FRAMEWORKS,
    "pyproject.toml": _PYTHON_FRAMEWORKS,
    "requirements.txt": _PYTHON_FRAMEWORKS,
    "go.mod": _GO_FRAMEWORKS,
    "Cargo.toml": _RUST_FRAMEWORKS,
    "Gemfile": _RUBY_FRAMEWORKS,
}

Confidence = Literal["high", "medium", "low"]


class GitHubToolError(RuntimeError):
    """The MCP server answered a tool call with an error result."""


@dataclass
class GitHubProfile:
    org: str
    org_url: str
    # high: a repo's homepage is on the company's domain. medium: the org login
    # came from the domain. low: the login was guessed from the name alone.
    confidence: Confidence
    repos_sampled: int
    top_languages: list[tuple[str, int]] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    notable_repos: list[dict] = field(default_factory=list)
    last_pushed_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt(self) -> str:
        languages = ", ".join(f"{lang} ({n} repos)" for lang, n in self.top_languages)
        repos = "\n".join(
            f"  - {r['name']} ({r['stars']} stars, {r['language'] or 'n/a'}): "
            f"{r['description'] or 'no description'}"
            for r in self.notable_repos
        )
        return (
            f"GitHub org: {self.org} ({self.org_url}), match confidence: {self.confidence}\n"
            f"Languages across {self.repos_sampled} top repos: {languages or 'unknown'}\n"
            f"Frameworks in dependency manifests: {', '.join(self.frameworks) or 'none found'}\n"
            f"Most recent push: {self.last_pushed_at or 'unknown'}\n"
            f"Notable repos:\n{repos or '  (none)'}"
        )


def _domain_root(domain: str | None) -> str | None:
    if not domain:
        return None
    host = urlparse(domain if "//" in domain else f"//{domain}").hostname or ""
    host = host.removeprefix("www.")
    return host or None


def candidate_org_slugs(company_name: str, domain: str | None = None) -> list[str]:
    """GitHub logins worth trying for a company, most likely first."""
    candidates: list[str] = []
    root = _domain_root(domain)
    if root:
        candidates.append(root.split(".")[0])

    words = re.findall(r"[a-z0-9]+", company_name.lower().replace("&", " and "))
    core = [w for w in words if w not in _COMPANY_SUFFIXES] or words
    candidates += ["".join(core), "-".join(core), "".join(words)]

    seen: list[str] = []
    for slug in candidates:
        if slug and _GITHUB_LOGIN.match(slug) and slug not in seen:
            seen.append(slug)
    return seen[:4]


def extract_frameworks(filename: str, content: str) -> set[str]:
    """Framework labels named as dependencies in one manifest file."""
    known = MANIFESTS.get(filename)
    if not known:
        return set()

    if filename == "package.json":
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return set()
        deps: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            if isinstance(data.get(key), dict):
                deps.update(data[key])
        return {label for dep, label in known.items() if dep in deps}

    found = set()
    for dep, label in known.items():
        # Bounded on both sides so "torch" does not match "torchvision" and
        # "flask" does not match "flask-cors".
        if re.search(rf"(?<![\w./-]){re.escape(dep)}(?![\w-])", content, re.IGNORECASE):
            found.add(label)
    return found


async def _search_org(call: ToolCaller, slug: str) -> list[dict]:
    try:
        text = await call(
            "search_repositories",
            {
                "query": f"org:{slug} archived:false",
                "sort": "stars",
                "order": "desc",
                "perPage": REPOS_SAMPLED,
                "minimal_output": False,
            },
        )
        items = json.loads(text).get("items", [])
    except (GitHubToolError, json.JSONDecodeError, AttributeError) as e:
        # A nonexistent org is a 422 from the search API; that just means
        # "not this slug".
        logger.debug("GitHub org %s not usable: %s", slug, e)
        return []
    return [r for r in items if isinstance(r, dict) and not r.get("fork")]


async def _repo_frameworks(call: ToolCaller, owner: str, repo: str) -> set[str]:
    try:
        listing = json.loads(
            await call(
                "get_file_contents",
                {"owner": owner, "repo": repo, "path": "/", "fields": ["name", "type"]},
            )
        )
    except (GitHubToolError, json.JSONDecodeError) as e:
        logger.debug("Could not list %s/%s: %s", owner, repo, e)
        return set()

    present = [
        entry["name"]
        for entry in listing
        if isinstance(entry, dict)
        and entry.get("type") == "file"
        and entry.get("name") in MANIFESTS
    ]

    async def read(name: str) -> set[str]:
        try:
            content = await call("get_file_contents", {"owner": owner, "repo": repo, "path": name})
        except GitHubToolError:
            return set()
        return extract_frameworks(name, content)

    found: set[str] = set()
    for labels in await asyncio.gather(*(read(name) for name in present)):
        found |= labels
    return found


async def research_github(
    company_name: str, call: ToolCaller, domain: str | None = None
) -> GitHubProfile | None:
    """Find the company's GitHub org and summarise it, or None if not found."""
    root = _domain_root(domain)
    from_domain = root.split(".")[0] if root else None

    org, repos = None, []
    for slug in candidate_org_slugs(company_name, domain):
        repos = await _search_org(call, slug)
        if repos:
            org = slug
            break
    if not org:
        return None

    owner = (repos[0].get("owner") or {}).get("login") or org
    homepages = {_domain_root(r.get("homepage")) for r in repos} - {None}
    if root and any(h == root or h.endswith(f".{root}") for h in homepages):
        confidence: Confidence = "high"
    elif org == from_domain:
        confidence = "medium"
    else:
        confidence = "low"

    languages = Counter(r["language"] for r in repos if r.get("language"))
    framework_sets = await asyncio.gather(
        *(_repo_frameworks(call, owner, r["name"]) for r in repos[:REPOS_INSPECTED])
    )
    pushed = [r["pushed_at"] for r in repos if r.get("pushed_at")]

    return GitHubProfile(
        org=owner,
        org_url=f"https://github.com/{owner}",
        confidence=confidence,
        repos_sampled=len(repos),
        top_languages=languages.most_common(5),
        frameworks=sorted(set().union(*framework_sets)),
        notable_repos=[
            {
                "name": r.get("name"),
                "url": r.get("html_url"),
                "stars": r.get("stargazers_count", 0),
                "language": r.get("language"),
                "description": (r.get("description") or "")[:200],
            }
            for r in repos[:5]
        ],
        last_pushed_at=max(pushed) if pushed else None,
    )


def _result_text(result) -> str:
    """Text of an MCP CallToolResult.

    File reads come back as a status line plus an embedded resource holding
    the file; the resource is the payload, so it wins when present.
    """
    texts, resources = [], []
    for block in result.content:
        resource = getattr(block, "resource", None)
        if resource is not None and getattr(resource, "text", None) is not None:
            resources.append(resource.text)
        elif getattr(block, "text", None) is not None:
            texts.append(block.text)
    return "\n".join(resources or texts)


def _root_cause(exc: BaseException) -> BaseException:
    """The first leaf of nested exception groups (the MCP transport wraps errors)."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


@asynccontextmanager
async def github_mcp_caller(settings: Settings) -> AsyncIterator[ToolCaller]:
    """A ToolCaller backed by one session on the remote GitHub MCP server."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "github": {
                "transport": "streamable_http",
                "url": settings.github_mcp_url,
                "headers": {
                    "Authorization": f"Bearer {settings.github_token}",
                    "X-MCP-Toolsets": "repos",
                    "X-MCP-Readonly": "true",
                },
                "timeout": 30,
            }
        }
    )
    async with client.session("github") as session:

        async def call(tool: str, args: dict) -> str:
            if tool not in ALLOWED_TOOLS:
                raise PermissionError(f"GitHub tool {tool!r} is not allowed")
            result = await session.call_tool(tool, args)
            text = _result_text(result)
            if result.isError:
                raise GitHubToolError(text)
            return text

        yield call


@asynccontextmanager
async def open_github_research(
    settings: Settings | None = None,
) -> AsyncIterator[ToolCaller | None]:
    """A GitHub ToolCaller, or None when GitHub research is unavailable.

    Unavailable means no token configured or the server could not be reached.
    Research is an enrichment, so neither case is an error for the caller.
    """
    settings = settings or get_settings()
    if not settings.github_token:
        yield None
        return

    async with AsyncExitStack() as stack:
        try:
            call = await stack.enter_async_context(github_mcp_caller(settings))
        except Exception as e:
            logger.warning("GitHub MCP unavailable, researching without it: %s", _root_cause(e))
            call = None
        yield call
