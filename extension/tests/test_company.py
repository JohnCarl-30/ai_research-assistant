"""The keyless dossier: which source feeds which, and how failures become gaps."""

import json

from fakes import FakeFetcher, fixture

from scout_mcp.company import research_company
from scout_mcp.notes import Notebook
from scout_mcp.sources import dnsinfo

HOMEPAGE = """<html><head><title>Acme</title><script src="/_next/static/x.js"></script></head>
<body><main><p>Acme builds robots.</p></main>
<a href="https://github.com/acme-hq">GitHub</a>
<a href="https://jobs.ashbyhq.com/acme-robots">Careers</a></body></html>"""

REPOS = {"items": [{"name": "core", "language": "Rust", "stargazers_count": 10,
                    "owner": {"login": "acme-hq"}, "pushed_at": "2026-09-01T00:00:00Z"}]}


async def fake_dns(domain):
    return dnsinfo.DnsInfo(email_provider=["Google Workspace"], verified_services=["Atlassian"])


def acme_fetcher(**extra) -> FakeFetcher:
    return FakeFetcher({
        **extra,
        "list=search": json.dumps({"query": {"search": []}}),
        "api.ashbyhq.com/posting-api/job-board/acme-robots": fixture("ashby_linear.json"),
        "search/repositories?q=org%3Aacme-hq": json.dumps(REPOS),
        "repos/acme-hq/core/contents/": "[]",
        "hn.algolia.com": json.dumps({"hits": [
            {"title": "Acme launches", "url": "https://acme.io/blog/launch", "points": 120,
             "num_comments": 40, "created_at": "2026-05-01T00:00:00Z", "objectID": "1"}]}),
        "https://acme.io/": HOMEPAGE,
    }, headers={"server": "Vercel"})


async def test_site_links_make_hiring_and_github_exact(tmp_path):
    notebook = Notebook(tmp_path / "notes.db")
    notebook.save("Acme interview", "Asked about robots.", tags=["acme"])
    fetcher = acme_fetcher()

    d = await research_company("Acme", domain="https://www.acme.io/about", fetcher=fetcher,
                               notebook=notebook, dns_lookup=fake_dns)

    assert (d.domain, d.domain_source) == ("acme.io", "given")
    assert d.website["tech"]["framework"] == ["Next.js"]
    assert d.website["tech"]["hosting"] == ["Vercel"]
    assert d.dns["email_provider"] == ["Google Workspace"]
    assert (d.hiring["slug"], d.hiring["board_source"]) == ("acme-robots", "website")
    assert (d.github["org"], d.github["org_source"], d.github["confidence"]) == (
        "acme-hq", "website", "high")
    assert d.hacker_news["top"][0]["title"] == "Acme launches"
    assert d.saved_notes[0]["title"] == "Acme interview"
    assert d.gaps == ["No Wikidata entry matched this company."]
    assert "web search" in d.next_steps[-1]
    # Exact links meant no slug guessing on job boards.
    assert not any("greenhouse" in url or "lever" in url for url, _ in fetcher.requests)


async def test_wikidata_found_under_the_subdomain_the_site_redirects_to():
    sparql = {"results": {"bindings": [{
        "item": {"value": "http://www.wikidata.org/entity/Q16639197"},
        "itemLabel": {"value": "Q16639197"},
        "website": {"value": "https://about.gitlab.com/"}}]}}

    class Redirecting(FakeFetcher):
        async def get(self, url, **kw):
            response = await super().get(url, **kw)
            if url == "https://gitlab.com/":
                response.url = "https://about.gitlab.com/"
            return response

    fetcher = Redirecting({
        "P856%3Dhttps%3A%2F%2Fgitlab.com": json.dumps({"query": {"search": []}}),
        "P856%3Dhttps%3A%2F%2Fabout.gitlab.com": json.dumps(
            {"query": {"search": [{"title": "Q16639197"}]}}),
        "sparql": json.dumps(sparql),
        "https://gitlab.com/": "<title>GitLab</title>",
    })

    d = await research_company("GitLab", domain="gitlab.com", fetcher=fetcher, notebook=None,
                               dns_lookup=fake_dns)

    assert d.facts["wikidata_id"] == "Q16639197" and d.facts["name"] == "GitLab"
    assert not any(g.startswith("No Wikidata entry") for g in d.gaps)


async def test_wikidata_supplies_the_domain_and_github_org():
    fetcher = FakeFetcher({
        "list=search": json.dumps({"query": {"search": [{"title": "Q7624104"}]}}),
        "sparql": fixture("wikidata_sparql.json"),
        "search/repositories?q=org%3Astripe": json.dumps(
            {"items": [{"name": "stripe-node", "language": "TypeScript",
                        "owner": {"login": "stripe"}}]}),
        "contents/": "[]",
    })

    d = await research_company("Stripe", domain=None, fetcher=fetcher, notebook=None,
                               dns_lookup=fake_dns)

    assert (d.domain, d.domain_source) == ("stripe.com", "wikidata")
    assert d.facts["founded"] == "2010"
    assert (d.github["org_source"], d.github["confidence"]) == ("wikidata", "high")


async def test_unknown_domain_asks_claude_to_find_it_and_still_tries_the_rest():
    fetcher = FakeFetcher({"list=search": json.dumps({"query": {"search": []}})})

    d = await research_company("Nowhere Labs", domain=None, fetcher=fetcher, notebook=None,
                               dns_lookup=fake_dns)

    assert d.domain is None and d.website is None and d.dns is None
    assert "find the company's official website" in d.next_steps[0].lower()
    assert any("Website unknown" in g for g in d.gaps)
    assert any("job board" in g for g in d.gaps)
    assert any("GitHub organisation" in g for g in d.gaps)


async def test_every_source_failing_still_returns_a_dossier():
    async def broken_dns(domain):
        raise OSError("resolver down")

    fetcher = FakeFetcher({"": (500, "server error")})  # every request fails

    d = await research_company("Acme", domain="acme.io", fetcher=fetcher, notebook=None,
                               dns_lookup=broken_dns)

    assert d.domain == "acme.io"
    sources = ["Wikidata", "Website", "DNS", "Hacker News", "Job board", "GitHub"]
    for source in sources:
        assert any(g.startswith(source) for g in d.gaps), (source, d.gaps)


async def test_github_profile_website_is_the_last_resort_for_the_org():
    repos = {"items": [{"name": "gitlabhq", "full_name": "gitlabhq/gitlabhq", "language": "Ruby",
                        "owner": {"login": "gitlabhq"}, "default_branch": "master"}]}
    fetcher = FakeFetcher({
        "list=search": json.dumps({"query": {"search": []}}),
        "search/repositories?q=org%3Agitlabhq": json.dumps(repos),
        "search/repositories": json.dumps({"items": []}),  # name guesses find nothing
        "search/users": json.dumps({"items": [{"login": "gitlabhq"}]}),
        "/orgs/gitlabhq": json.dumps({"blog": "https://about.gitlab.com"}),
    })

    d = await research_company("GitLab", domain="gitlab.com", fetcher=fetcher, notebook=None,
                               dns_lookup=fake_dns)

    assert (d.github["org"], d.github["org_source"], d.github["confidence"]) == (
        "gitlabhq", "github profile", "high")


async def test_a_namesake_org_guessed_from_the_domain_loses_to_the_listed_one():
    # pleo.io's org is pleo-io; "pleo" (guessed from the domain) is someone else.
    def repos(owner):
        return json.dumps({"items": [{"name": "app", "full_name": f"{owner}/app",
                                      "language": "Kotlin", "owner": {"login": owner},
                                      "default_branch": "main"}]})

    fetcher = FakeFetcher({
        "list=search": json.dumps({"query": {"search": []}}),
        "search/repositories?q=org%3Apleo-io": repos("pleo-io"),
        "search/repositories?q=org%3Apleo": repos("pleo"),
        "search/users": json.dumps({"items": [{"login": "pleo"}, {"login": "pleo-io"}]}),
        "/orgs/pleo-io": json.dumps({"blog": "https://www.pleo.io"}),
        "/orgs/pleo": json.dumps({"blog": "https://pleo.example"}),
    })

    d = await research_company("Pleo", domain="pleo.io", fetcher=fetcher, notebook=None,
                               dns_lookup=fake_dns)

    assert (d.github["org"], d.github["org_source"]) == ("pleo-io", "github profile")
