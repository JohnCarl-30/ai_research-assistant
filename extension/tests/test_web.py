import httpx
import pytest

from scout_mcp import web

DDG_HTML = """
<div class="result">
  <a class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Facme.io%2Fabout&rut=x">Acme - About</a>
  <a class="result__snippet">Acme builds <b>robots</b>.</a>
</div>
<div class="result">
  <a class="result__a" href="https://duckduckgo.com/y.js?ad_provider=x">Ad</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/direct">Direct</a>
</div>
"""


def test_parse_duckduckgo_unwraps_redirects_and_skips_ads():
    results = web.parse_duckduckgo_html(DDG_HTML, limit=5)
    assert [r.url for r in results] == ["https://acme.io/about", "https://example.com/direct"]
    assert results[0].snippet == "Acme builds robots ."
    assert len(web.parse_duckduckgo_html(DDG_HTML, limit=1)) == 1


def test_duckduckgo_captcha_is_detected_not_read_as_no_results():
    challenge = '<div class="anomaly-modal__title">Unfortunately, bots use DuckDuckGo too.</div>'
    assert web.is_duckduckgo_challenge(202, "")
    assert web.is_duckduckgo_challenge(200, challenge)
    assert not web.is_duckduckgo_challenge(200, DDG_HTML)
    assert web.parse_duckduckgo_html(challenge, 5) == []  # why detection is needed


def test_html_to_text_keeps_main_content():
    html = """<html><head><title>Acme</title><script>evil()</script></head>
    <body><nav>Menu</nav><main><h1>About</h1><p>We build robots.</p></main>
    <footer>(c)</footer></body></html>"""
    assert web.html_to_text(html) == ("Acme", "About\nWe build robots.")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/admin",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://[::1]/",
        "http://[::ffff:192.168.1.1]/",
        "file:///etc/passwd",
        "ftp://example.com/",
    ],
)
async def test_non_public_urls_are_refused(url):
    with pytest.raises(web.BlockedURLError):
        await web.read_page(url)


async def test_redirects_to_private_addresses_are_refused(monkeypatch):
    # The event hook runs per request, so a public page redirecting inward fails.
    async def fake_ensure(url):
        if "127.0.0.1" in url:
            raise web.BlockedURLError("not public")

    def handler(request):
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
        return httpx.Response(200, text="secret")

    monkeypatch.setattr(web, "ensure_public_url", fake_ensure)
    original = web.public_client
    monkeypatch.setattr(
        web, "public_client", lambda: original(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(web.BlockedURLError):
        await web.read_page("http://public.example/")


async def test_search_prefers_configured_provider(monkeypatch):
    calls = []

    async def fake(name):
        async def provider(query, limit, *key):
            calls.append((name, query, limit, key))
            return []
        return provider

    monkeypatch.setattr(web, "brave_search", await fake("brave"))
    monkeypatch.setattr(web, "firecrawl_search", await fake("firecrawl"))
    monkeypatch.setattr(web, "duckduckgo_search", await fake("ddg"))

    assert (await web.search("q", 50, brave_api_key="b", firecrawl_api_key="f"))[0] == "brave"
    assert (await web.search("q", 5, firecrawl_api_key="f"))[0] == "firecrawl"
    assert (await web.search("q", 5))[0] == "duckduckgo"
    assert calls[0] == ("brave", "q", 20, ("b",))  # limit clamped
