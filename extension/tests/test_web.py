import httpx
import pytest

from scout_mcp import web


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
