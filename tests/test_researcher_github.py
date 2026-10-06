"""Company research with GitHub signals. The GitHub core is tested in extension/tests."""

from types import SimpleNamespace

from scout_mcp.github import GitHubToolError

from app.agents import researcher
from app.agents.github_research import open_github_research
from app.config import get_settings


async def test_open_github_research_is_none_without_token():
    settings = get_settings().model_copy(update={"github_token": None})
    async with open_github_research(settings) as github:
        assert github is None


async def _fake_github(tool, args):
    if tool == "search_repositories":
        if args["query"].startswith("org:acme "):
            return '{"items": [{"name": "api", "language": "Go", "stargazers_count": 1, ' \
                '"owner": {"login": "Acme"}}]}'
        raise GitHubToolError("422")
    if args["path"] == "/":
        return '[{"name": "go.mod", "type": "file"}]'
    return "require google.golang.org/grpc v1.60.0"


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
    result = await researcher.research_company("Acme", github=_fake_github)

    assert result["github"]["org"] == "Acme"
    assert "Frameworks in dependency manifests: grpc" in prompts[0]
