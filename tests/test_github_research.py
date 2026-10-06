"""GitHub research tool, against a fake GitHub MCP server. No network."""

import json
from types import SimpleNamespace

from mcp.types import CallToolResult, EmbeddedResource, TextContent, TextResourceContents

from app.agents import researcher
from app.agents.github_research import (
    ALLOWED_TOOLS,
    GitHubToolError,
    _result_text,
    candidate_org_slugs,
    extract_frameworks,
    open_github_research,
    research_github,
)
from app.config import get_settings


def _repo(name, language, stars, homepage=None, fork=False, pushed="2026-09-01T00:00:00Z"):
    return {
        "name": name,
        "html_url": f"https://github.com/acme/{name}",
        "description": f"{name} service",
        "language": language,
        "stargazers_count": stars,
        "homepage": homepage,
        "fork": fork,
        "pushed_at": pushed,
        "owner": {"login": "Acme", "type": "Organization"},
    }


class FakeGitHub:
    """Answers the two tools like the GitHub MCP server does, and logs calls."""

    def __init__(self, orgs: dict[str, list[dict]], files: dict[tuple[str, str], str]):
        self.orgs = orgs
        self.files = files
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, tool: str, args: dict) -> str:
        assert tool in ALLOWED_TOOLS
        self.calls.append((tool, args))
        if tool == "search_repositories":
            slug = args["query"].split()[0].removeprefix("org:")
            if slug not in self.orgs:
                raise GitHubToolError("422 Validation Failed")
            return json.dumps({"total_count": len(self.orgs[slug]), "items": self.orgs[slug]})

        repo, path = args["repo"], args["path"]
        if path == "/":
            names = [p for (r, p) in self.files if r == repo]
            return json.dumps([{"name": n, "type": "file"} for n in names + ["README.md"]])
        if (repo, path) not in self.files:
            raise GitHubToolError("404 Not Found")
        return self.files[(repo, path)]


ACME_REPOS = [
    _repo("api", "Go", 900, homepage="https://docs.acme.io"),
    _repo("web", "TypeScript", 500),
    _repo("ml", "Python", 300, pushed="2026-09-30T00:00:00Z"),
    _repo("tools", "Go", 50),
    _repo("forked-lib", "C", 9999, fork=True),
]
ACME_FILES = {
    ("api", "go.mod"): "module acme/api\n\nrequire (\n\tgoogle.golang.org/grpc v1.60.0\n)\n",
    ("web", "package.json"): json.dumps(
        {
            "dependencies": {"next": "16.0.0", "react": "19.0.0"},
            "devDependencies": {"typescript": "5"},
        }
    ),
    ("ml", "requirements.txt"): "fastapi==0.110\ntorchvision==0.19\n",
    ("tools", "Cargo.toml"): '[dependencies]\ntokio = "1"\n',  # beyond REPOS_INSPECTED
}


def test_candidate_slugs_prefer_domain_and_drop_legal_suffixes():
    assert candidate_org_slugs("Stripe, Inc.") == ["stripe", "stripeinc"]
    assert candidate_org_slugs("Acme Robotics LLC", domain="https://www.acme.io/careers") == [
        "acme",
        "acmerobotics",
        "acme-robotics",
        "acmeroboticsllc",
    ]
    assert candidate_org_slugs("!!!") == []


def test_extract_frameworks_reads_dependencies_not_substrings():
    assert extract_frameworks("package.json", ACME_FILES[("web", "package.json")]) == {
        "next.js",
        "react",
        "typescript",
    }
    # torchvision is not torch; flask-cors is not flask.
    manifest = "torchvision\nflask-cors\nDjango>=5\n"
    assert extract_frameworks("requirements.txt", manifest) == {"django"}
    assert extract_frameworks("package.json", "{not json") == set()
    assert extract_frameworks("README.md", "react") == set()


async def test_research_github_profiles_the_org():
    gh = FakeGitHub(orgs={"acme": ACME_REPOS}, files=ACME_FILES)

    profile = await research_github("Acme Corp", gh, domain="acme.io")

    assert profile is not None
    assert profile.org == "Acme"
    assert profile.confidence == "high"  # a repo homepage is on acme.io
    assert profile.repos_sampled == 4  # the fork is excluded
    assert profile.top_languages[0] == ("Go", 2)
    assert profile.frameworks == ["fastapi", "grpc", "next.js", "react", "typescript"]
    assert profile.last_pushed_at == "2026-09-30T00:00:00Z"
    assert [r["name"] for r in profile.notable_repos] == ["api", "web", "ml", "tools"]
    assert "GitHub org: Acme" in profile.to_prompt()
    # Only the top REPOS_INSPECTED repos have their files read.
    assert not any(args.get("repo") == "tools" for _, args in gh.calls)


async def test_research_github_falls_through_slugs_and_rates_name_guesses_low():
    gh = FakeGitHub(orgs={"acme-robotics": ACME_REPOS[:1]}, files={})

    profile = await research_github("Acme Robotics", gh)

    assert profile is not None
    assert profile.confidence == "low"
    assert profile.frameworks == []
    searched = [a["query"] for t, a in gh.calls if t == "search_repositories"]
    assert searched == ["org:acmerobotics archived:false", "org:acme-robotics archived:false"]


async def test_research_github_returns_none_when_no_org_matches():
    assert await research_github("Nobody Ltd", FakeGitHub(orgs={}, files={})) is None


def test_result_text_prefers_embedded_file_over_status_line():
    result = CallToolResult(
        content=[
            TextContent(type="text", text="successfully downloaded text file"),
            EmbeddedResource(
                type="resource",
                resource=TextResourceContents(uri="repo://a/b/contents/go.mod", text="module x"),
            ),
        ]
    )
    assert _result_text(result) == "module x"
    assert _result_text(CallToolResult(content=[TextContent(type="text", text="{}")])) == "{}"


async def test_open_github_research_is_none_without_token():
    settings = get_settings().model_copy(update={"github_token": None})
    async with open_github_research(settings) as github:
        assert github is None


async def test_research_company_survives_github_failure(monkeypatch):
    prompts = []

    async def fake_invoke(messages):
        prompts.append(messages[0].content)
        return SimpleNamespace(content="analysis")

    async def broken(tool, args):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(researcher, "llm", SimpleNamespace(ainvoke=fake_invoke))

    result = await researcher.research_company("Acme", github=broken)

    assert result["raw_response"] == "analysis"
    assert result["github"] is None
    assert "GitHub signals: Not available" in prompts[0]


async def test_research_company_includes_github_signals(monkeypatch):
    prompts = []

    async def fake_invoke(messages):
        prompts.append(messages[0].content)
        return SimpleNamespace(content="analysis")

    monkeypatch.setattr(researcher, "llm", SimpleNamespace(ainvoke=fake_invoke))
    gh = FakeGitHub(orgs={"acme": ACME_REPOS}, files=ACME_FILES)

    result = await researcher.research_company("Acme", github=gh)

    assert result["github"]["org"] == "Acme"
    assert "Frameworks in dependency manifests: fastapi, grpc" in prompts[0]
