"""HTTP for the keyless sources: one cache, one User-Agent, public addresses only.

Keyless APIs ration by IP (GitHub's search API allows 10 requests a minute
without a token), so every successful response is cached in SQLite for a per-source time.
Researching the same company twice in a day costs nothing the second time.
"""

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scout_mcp import __version__
from scout_mcp.web import public_client

# Wikimedia's policy requires a descriptive User-Agent; others appreciate one.
USER_AGENT = f"ScoutResearch/{__version__} (company research MCP server; local, per-user)"
MAX_BYTES = 5_000_000

HOUR = 3600
DAY = 24 * HOUR


class FetchError(RuntimeError):
    def __init__(self, url: str, status: int, message: str = ""):
        super().__init__(message or f"HTTP {status} from {url}")
        self.url = url
        self.status = status


@dataclass
class Response:
    url: str
    status: int
    headers: dict[str, str]
    text: str

    def json(self) -> Any:
        return json.loads(self.text)


class Cache:
    """A key-value cache with expiry, in one SQLite file."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, stored REAL, value TEXT)"
        )

    def get(self, key: str, ttl: float) -> Any | None:
        row = self.db.execute("SELECT stored, value FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None or time.time() - row[0] > ttl:
            return None
        return json.loads(row[1])

    def set(self, key: str, value: Any) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO cache (key, stored, value) VALUES (?, ?, ?)",
                (key, time.time(), json.dumps(value)),
            )

    def close(self) -> None:
        self.db.close()


class Fetcher:
    """Cached GETs to public addresses. Only 2xx responses are cached."""

    def __init__(self, cache: Cache | None = None):
        self.cache = cache

    async def get(
        self,
        url: str,
        *,
        ttl: float,
        headers: dict[str, str] | None = None,
        max_bytes: int = MAX_BYTES,
    ) -> Response:
        # Credentials never go into the key: the cache is a plain file on disk.
        keyed = {k: v for k, v in (headers or {}).items() if k.lower() != "authorization"}
        key = f"GET {url} {json.dumps(keyed, sort_keys=True)}"
        if self.cache is not None and (hit := self.cache.get(key, ttl)) is not None:
            return Response(**hit)

        async with public_client(timeout=30) as client:
            client.headers["User-Agent"] = USER_AGENT
            async with client.stream("GET", url, headers=headers) as r:
                body = bytearray()
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        break
                response = Response(
                    url=str(r.url),
                    status=r.status_code,
                    headers={k.lower(): v for k, v in r.headers.items()},
                    text=body.decode(r.encoding or "utf-8", errors="replace"),
                )

        if not 200 <= response.status < 300:
            raise FetchError(url, response.status, _error_message(response))
        if self.cache is not None:
            self.cache.set(key, response.__dict__)
        return response

    async def get_json(self, url: str, *, ttl: float, headers: dict | None = None) -> Any:
        response = await self.get(
            url, ttl=ttl, headers={"Accept": "application/json", **(headers or {})}
        )
        return response.json()


def _error_message(response: Response) -> str:
    try:
        detail = response.json().get("message", "")
    except (ValueError, AttributeError):
        detail = ""
    return f"HTTP {response.status} from {response.url}" + (f": {detail}" if detail else "")
