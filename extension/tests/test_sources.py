"""Keyless sources, parsed from trimmed copies of real API responses."""

import json

import httpx
import pytest
from fakes import FakeFetcher, fixture

from scout_mcp.github import GitHubToolError, research_github
from scout_mcp.sources import dnsinfo, hn, jobs, site, wikidata
from scout_mcp.sources.github_rest import GitHubRateLimitError, github_rest_caller
from scout_mcp.sources.http import Cache, Fetcher, Response

# --- Wikidata -----------------------------------------------------------------


def test_wikidata_merges_rows_and_keeps_the_latest_headcount():
    facts = wikidata.parse_facts(json.loads(fixture("wikidata_sparql.json")))
    stripe = facts["Q7624104"]
    assert (stripe.name, stripe.website, stripe.founded, stripe.github) == (
        "Stripe", "https://stripe.com/", "2010", "stripe"
    )
    assert (stripe.employees, stripe.employees_as_of) == (8000, "2023-01-01")
    assert stripe.headquarters == ["San Francisco", "South San Francisco"]
    assert stripe.parent == []  # unlabeled items arrive as bare Q-ids and are dropped
    assert facts["Q999567"].ticker == ["LLTC"]


async def test_wikidata_by_website_is_trusted():
    fetcher = FakeFetcher({
        "list=search": json.dumps({"query": {"search": [{"title": "Q7624104"}]}}),
        "sparql": fixture("wikidata_sparql.json"),
    })
    result = await wikidata.lookup(fetcher, "Stripe", "stripe.com")
    assert result.facts.wikidata_id == "Q7624104" and result.facts.match == "website"
    search_url = fetcher.requests[0][0]
    assert "P856%3Dhttps%3A%2F%2Fstripe.com%2F" in search_url


async def test_wikidata_never_guesses_between_similar_names():
    # The real candidates for "Linear": none is Linear the issue tracker.
    fetcher = FakeFetcher({
        "list=search": json.dumps({"query": {"search": [
            {"title": "Q999567"}, {"title": "Q16572717"}, {"title": "Q137463817"}]}}),
        "sparql": fixture("wikidata_sparql.json"),
    })
    result = await wikidata.lookup(fetcher, "Linear", None)
    assert result.facts is None and result.ambiguous == []

    exact = await wikidata.lookup(fetcher, "Linear Labs", None)  # "Linear Labs, Inc."
    assert exact.facts.wikidata_id == "Q137463817" and exact.facts.match == "name"


async def test_wikidata_website_mismatch_is_rejected():
    fetcher = FakeFetcher({
        "list=search": json.dumps({"query": {"search": [{"title": "Q999567"}]}}),
        "sparql": fixture("wikidata_sparql.json"),
    })
    assert (await wikidata.lookup(fetcher, "Linear", "linear.app")).facts is None


# --- Job boards ---------------------------------------------------------------


def test_greenhouse_hiring_signals_from_real_postings():
    h = jobs.summarize("greenhouse", "vercel", "website",
                       jobs.parse_greenhouse(json.loads(fixture("greenhouse_vercel.json"))))
    assert h.open_roles == 6
    assert h.by_department[0] == ("Engineering", 3)
    assert dict(h.tech_mentions)["TypeScript"] == 3
    assert {"React", "Next.js", "Go"} <= set(dict(h.tech_mentions))
    assert h.board_url == "https://job-boards.greenhouse.io/vercel"


def test_ashby_hiring_signals_from_real_postings():
    h = jobs.summarize("ashby", "linear", "guess",
                       jobs.parse_ashby(json.loads(fixture("ashby_linear.json"))))
    assert h.remote_share == 1.0
    assert dict(h.by_department) == {"Product": 4, "GTM": 2}
    assert {"TypeScript", "GraphQL"} <= set(dict(h.tech_mentions))


def test_lever_parsing():
    posting = {
        "text": "Backend Engineer", "categories": {"team": "Platform", "location": "Remote - US"},
        "descriptionPlain": "We use Golang, PostgreSQL and Kubernetes.",
        "lists": [{"text": "Requirements", "content": "<li>Experience with Kafka</li>"}],
        "hostedUrl": "https://jobs.lever.co/acme/1", "workplaceType": "remote",
    }
    (job,) = jobs.parse_lever([posting])
    assert (job.department, job.remote) == ("Platform", True)
    assert {"Go", "PostgreSQL", "Kubernetes", "Kafka"} <= set(dict(jobs.tech_mentions([job])))


def test_tech_terms_skip_ordinary_english():
    job = jobs.Job("t", None, None, False, None,
                   "Go-to-market lead. React to feedback, go to events. We use Java and Rails.")
    assert set(dict(jobs.tech_mentions([job]))) == {"Java", "Rails"}


async def test_find_hiring_prefers_the_board_the_site_links_to():
    fetcher = FakeFetcher({"api.ashbyhq.com/posting-api/job-board/linear-app":
                           fixture("ashby_linear.json")})
    h = await jobs.find_hiring(fetcher, [("ashby", "linear-app")], guesses=["linear"])
    assert (h.slug, h.board_source) == ("linear-app", "website")
    assert len(fetcher.requests) == 1


async def test_one_board_being_down_does_not_hide_another():
    fetcher = FakeFetcher({
        "boards-api.greenhouse.io": (503, "unavailable"),
        "api.ashbyhq.com/posting-api/job-board/acme": fixture("ashby_linear.json"),
    })
    h = await jobs.find_hiring(fetcher, [], guesses=["acme"])
    assert h.board == "ashby"

    nothing = FakeFetcher({"boards-api.greenhouse.io": (503, "unavailable")})
    with pytest.raises(jobs.JobBoardsUnavailableError, match="greenhouse"):
        await jobs.find_hiring(nothing, [], guesses=["acme"])


async def test_find_hiring_falls_back_to_guesses_and_skips_empty_boards():
    fetcher = FakeFetcher({
        "api.lever.co/v0/postings/acme": "[]",  # Lever answers unknown boards with []
        "api.ashbyhq.com/posting-api/job-board/acme": fixture("ashby_linear.json"),
    })
    h = await jobs.find_hiring(fetcher, [], guesses=["acme"])
    assert (h.board, h.board_source) == ("ashby", "guess")


# --- Website ------------------------------------------------------------------

HOMEPAGE = """<html><head><title>Acme - Robots for everyone</title>
<meta name="description" content="Acme builds friendly robots.">
<link rel="alternate" type="application/rss+xml" href="/blog/rss.xml">
<script src="/_next/static/chunks/main.js"></script>
<script src="https://www.googletagmanager.com/gtag/js"></script>
<script src="https://js.stripe.com/v3"></script></head>
<body><nav>Menu</nav><main><h1>Robots</h1><p>We build robots for homes.</p></main>
<footer><a href="https://github.com/acme-robots">GitHub</a>
<a href="https://github.com/about">About GitHub</a>
<a href="/careers">Careers</a><a href="https://www.linkedin.com/company/acme">in</a></footer>
</body></html>"""


def test_parse_page_fingerprints_and_extracts_links():
    page = Response(url="https://acme.io/", status=200,
                    headers={"server": "Vercel", "x-vercel-id": "1"}, text=HOMEPAGE)
    info = site.parse_page(page, "acme.io")
    assert info.title == "Acme - Robots for everyone"
    assert info.description == "Acme builds friendly robots."
    assert info.tech == {"framework": ["Next.js"], "hosting": ["Vercel"],
                         "analytics": ["Google Tag Manager"], "payments": ["Stripe"]}
    assert info.github_orgs == ["acme-robots"]
    assert info.careers_url == "https://acme.io/careers"
    assert info.feeds == ["https://acme.io/blog/rss.xml"]
    assert info.about == "Robots We build robots for homes."


async def test_inspect_follows_careers_page_to_find_the_job_board():
    fetcher = FakeFetcher({
        "acme.io/careers": '<a href="https://jobs.ashbyhq.com/acme-robots">Open roles</a>',
        "acme.io/": HOMEPAGE,
    })
    info = await site.inspect(fetcher, "acme.io")
    assert info.job_boards == [("ashby", "acme-robots")]


# --- DNS ----------------------------------------------------------------------


def test_dns_classification():
    info = dnsinfo.classify(
        ["aspmx.l.google.com", "alt1.aspmx.l.google.com"],
        [
            "v=spf1 include:_spf.google.com include:sendgrid.net include:servers.mcsv.net ~all",
            "google-site-verification=abc",
            "atlassian-domain-verification=xyz",
            "MS=ms123",
            "openai-domain-verification=dv-1",
            "some unrelated text",
        ],
    )
    assert info.email_provider == ["Google Workspace"]
    assert info.email_senders == ["Google Workspace", "SendGrid", "Mailchimp"]
    assert info.verified_services == ["Google", "Atlassian", "Microsoft 365", "openai"]


async def test_dns_failures_are_reported_not_mistaken_for_no_records():
    import dns.exception
    import dns.resolver

    class Resolver:
        async def resolve(self, domain, kind):
            if kind == "TXT":
                raise dns.exception.Timeout()
            raise dns.resolver.NoAnswer()

    info = await dnsinfo.lookup("acme.io", resolver=Resolver())
    assert info.email_provider == [] and info.unavailable == ["TXT"]


# --- Hacker News --------------------------------------------------------------


async def test_hn_keeps_only_stories_on_the_domain():
    hits = {"hits": [
        {"title": "Linear – A fast issue tracker", "url": "http://linear.app/", "points": 491,
         "num_comments": 221, "created_at": "2020-06-30T18:16:16Z", "objectID": "23693029"},
        {"title": "Not them", "url": "https://notlinear.app/x", "points": 9,
         "created_at": "2026-01-01T00:00:00Z", "objectID": "2"},
    ]}
    fetcher = FakeFetcher({"hn.algolia.com": json.dumps(hits)})
    result = await hn.stories(fetcher, "linear.app")
    assert [s["title"] for s in result["top"]] == ["Linear – A fast issue tracker"]
    assert result["top"][0]["discussion"] == "https://news.ycombinator.com/item?id=23693029"
    assert result["last_story"] == "2020-06-30"


# --- GitHub over REST ---------------------------------------------------------


async def test_github_research_uses_only_the_search_api_and_raw_files():
    repos = {"items": [{"name": "stripe-node", "full_name": "stripe/stripe-node",
                        "default_branch": "master", "language": "TypeScript",
                        "stargazers_count": 4000, "owner": {"login": "stripe"},
                        "pushed_at": "2026-09-01T00:00:00Z"}]}
    fetcher = FakeFetcher({
        "api.github.com/search/repositories": json.dumps(repos),
        "raw.githubusercontent.com/stripe/stripe-node/master/package.json": json.dumps(
            {"devDependencies": {"typescript": "5"}}),
    })
    profile = await research_github("Stripe", github_rest_caller(fetcher), org="stripe")

    assert (profile.org, profile.confidence) == ("stripe", "high")
    assert profile.frameworks == ["typescript"]
    api_calls = [u for u, _ in fetcher.requests if "api.github.com" in u]
    assert len(api_calls) == 1 and "/search/repositories?q=org%3Astripe" in api_calls[0]
    # Files come from the repo's real default branch, never the core API.
    raw = [u for u, _ in fetcher.requests if "raw.githubusercontent.com" in u]
    assert raw and all("/stripe/stripe-node/master/" in u for u in raw)


async def test_github_rate_limit_is_an_error_not_a_missing_org():
    fetcher = FakeFetcher({"api.github.com": (403, "API rate limit exceeded for 1.2.3.4.")})
    with pytest.raises(GitHubRateLimitError, match="10 a minute"):
        await research_github("Stripe", github_rest_caller(fetcher), org="stripe")


async def test_raw_files_fall_back_to_head_when_the_branch_is_unknown():
    fetcher = FakeFetcher({"raw.githubusercontent.com/acme/app/HEAD/go.mod": "module acme"})
    call = github_rest_caller(fetcher)
    listing = json.loads(await call("get_file_contents",
                                    {"owner": "acme", "repo": "app", "path": "/"}))
    assert listing == [{"name": "go.mod", "type": "file"}]
    with pytest.raises(GitHubToolError):
        await call("get_file_contents", {"owner": "acme", "repo": "app", "path": "Gemfile"})


# --- Cache --------------------------------------------------------------------


async def test_cache_serves_repeats_and_never_stores_credentials(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    async def allow(url):
        return None

    monkeypatch.setattr("scout_mcp.web.ensure_public_url", allow)
    monkeypatch.setattr(
        "scout_mcp.sources.http.public_client",
        lambda timeout=30: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    cache = Cache(tmp_path / "cache.db")
    fetcher = Fetcher(cache)
    secret = {"Authorization": "Bearer ghp_secret"}

    url = "https://api.example.com/x"
    assert await fetcher.get_json(url, ttl=60, headers=secret) == {"ok": True}
    assert await fetcher.get_json(url, ttl=60, headers=secret) == {"ok": True}
    assert len(calls) == 1
    assert b"ghp_secret" not in (tmp_path / "cache.db").read_bytes()
    assert await fetcher.get_json(url, ttl=0, headers=secret)
    assert len(calls) == 2  # expired entries are refetched
