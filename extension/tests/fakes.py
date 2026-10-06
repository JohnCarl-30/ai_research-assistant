"""Test helpers shared by the extension's tests."""

from pathlib import Path

from scout_mcp.sources.http import Fetcher, FetchError, Response

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class FakeFetcher(Fetcher):
    """Serves canned responses by URL substring (first match wins); others are 404."""

    def __init__(self, routes: dict[str, tuple[int, str] | str], headers: dict | None = None):
        super().__init__(cache=None)
        self.routes = routes
        self.headers = headers or {}
        self.requests: list[tuple[str, dict]] = []

    async def get(self, url, *, ttl, headers=None, max_bytes=0, cache=True):
        self.requests.append((url, headers or {}))
        for needle, answer in self.routes.items():
            if needle in url:
                status, text = answer if isinstance(answer, tuple) else (200, answer)
                if not 200 <= status < 300:
                    raise FetchError(url, status, f"HTTP {status} from {url}: {text}")
                return Response(url=url, status=status, headers=self.headers, text=text)
        raise FetchError(url, 404)
