import json
from contextlib import asynccontextmanager

from scout_mcp.company import ANGLES, guess_domain, research_company
from scout_mcp.github import GitHubToolError
from scout_mcp.notes import Notebook
from scout_mcp.web import Page, SearchResult


def _r(url, title="t"):
    return SearchResult(title=title, url=url, snippet="s")


def test_guess_domain_skips_aggregators_and_needs_a_name_match():
    results = [
        _r("https://www.linkedin.com/company/acme-robotics"),
        _r("https://acme.ai/"),  # "acme" alone is not a slug of "Acme Robotics"
        _r("https://careers.acme-robotics.io/jobs"),
    ]
    assert guess_domain("Acme Robotics", results) == "acme-robotics.io"
    assert guess_domain("Acme Robotics", results[:2]) is None
    assert guess_domain("Stripe, Inc.", [_r("https://stripe.com/about")]) == "stripe.com"


class Recorder:
    def __init__(self, fail_on: str | None = None):
        self.queries, self.reads = [], []
        self.fail_on = fail_on

    async def search(self, query, limit):
        self.queries.append(query)
        if self.fail_on and self.fail_on in query:
            raise RuntimeError("429 rate limited")
        return [_r("https://en.wikipedia.org/wiki/Acme"), _r("https://www.acme.io/")]

    async def read(self, url, max_chars):
        self.reads.append(url)
        return Page(url=url, title="Acme", text="We build robots.", truncated=False)


def _github(repos_by_org):
    async def call(tool, args):
        if tool == "search_repositories":
            org = args["query"].split()[0].removeprefix("org:")
            if org not in repos_by_org:
                raise GitHubToolError("422")
            return json.dumps({"items": repos_by_org[org]})
        return "[]"

    @asynccontextmanager
    async def opener():
        yield call

    return opener


async def test_dossier_resolves_domain_and_confirms_github(tmp_path):
    rec = Recorder()
    nb = Notebook(tmp_path / "notes.db")
    nb.save("Acme interview notes", "Acme asked about robots.", tags=["acme"])
    repos = [{"name": "core", "language": "Rust", "stargazers_count": 10,
              "homepage": "https://acme.io", "owner": {"login": "acme"}}]

    d = await research_company(
        "Acme", domain=None, search=rec.search, read=rec.read,
        open_github=_github({"acme": repos}), notebook=nb,
    )

    assert (d.domain, d.domain_source) == ("acme.io", "search")
    assert rec.reads == ["https://acme.io"]
    assert d.homepage["text"] == "We build robots."
    assert d.github["confidence"] == "high"  # homepage matches the resolved domain
    assert set(d.sources) == {key for key, _, _ in ANGLES}
    assert d.saved_notes[0]["title"] == "Acme interview notes"
    assert d.gaps == []


async def test_dossier_reports_gaps_instead_of_failing():
    rec = Recorder(fail_on="news")

    d = await research_company(
        "Acme", domain="https://www.acme.io/", search=rec.search, read=rec.read,
        open_github=None, notebook=None,
    )

    assert (d.domain, d.domain_source) == ("acme.io", "given")
    assert d.sources["news"] == []
    assert any("news search failed" in g for g in d.gaps)
    assert any("no GitHub token" in g for g in d.gaps)
    assert d.homepage is not None
