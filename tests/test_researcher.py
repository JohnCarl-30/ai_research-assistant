"""Company research: Scout's dossier as the LLM's evidence. The dossier itself is
tested in extension/tests."""

import json
from types import SimpleNamespace

from scout_mcp.sources import dnsinfo
from scout_mcp.sources.http import Fetcher, FetchError, Response

from app.agents import researcher


class FakeFetcher(Fetcher):
    """Serves canned responses by URL substring; everything else is a 404."""

    def __init__(self, routes: dict[str, str]):
        super().__init__(cache=None)
        self.routes = routes

    async def get(self, url, *, ttl, headers=None, max_bytes=0, cache=True):
        for needle, text in self.routes.items():
            if needle in url:
                return Response(url=url, status=200, headers={}, text=text)
        raise FetchError(url, 404)


def _capture(monkeypatch) -> list[str]:
    prompts = []

    async def fake_invoke(messages):
        prompts.append(messages[0].content)
        return SimpleNamespace(content="analysis")

    async def no_dns(domain):
        return dnsinfo.DnsInfo()

    monkeypatch.setattr(researcher, "llm", SimpleNamespace(ainvoke=fake_invoke))
    monkeypatch.setattr(dnsinfo, "lookup", no_dns)
    return prompts


async def test_research_cites_the_dossier(monkeypatch):
    prompts = _capture(monkeypatch)
    board = {"jobs": [{"title": "Backend Engineer", "location": {"name": "Remote"},
                       "departments": [{"name": "Engineering"}],
                       "content": "We use Go and PostgreSQL."}]}
    fetcher = FakeFetcher({"boards-api.greenhouse.io/v1/boards/acme/": json.dumps(board)})

    result = await researcher.research_company("Acme", domain="acme.com", fetcher=fetcher)

    assert result["raw_response"] == "analysis"
    assert result["dossier"]["hiring"]["open_roles"] == 1
    assert '"board": "greenhouse"' in prompts[0]
    assert "Go" in prompts[0] and "sample_roles" not in prompts[0]


async def test_research_survives_a_failing_dossier(monkeypatch):
    prompts = _capture(monkeypatch)

    async def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(researcher, "build_dossier", broken)
    result = await researcher.research_company("Acme")

    assert result["raw_response"] == "analysis"
    assert result["github"] is None
    assert "Dossier failed: boom" in prompts[0]
