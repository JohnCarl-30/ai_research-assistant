"""Extension settings, read from the environment.

Claude Desktop fills these from the install form (manifest.json user_config).
An optional field the user left blank can arrive as an empty string or, in some
hosts, as the unsubstituted ``${user_config.x}`` placeholder; both mean unset.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from scout_mcp.github import DEFAULT_GITHUB_MCP_URL


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("${"):
        return None
    return value


@dataclass(frozen=True)
class Config:
    data_dir: Path
    brave_api_key: str | None
    firecrawl_api_key: str | None
    github_token: str | None
    github_mcp_url: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            data_dir=Path(_env("SCOUT_DATA_DIR") or Path.home() / ".scout").expanduser(),
            brave_api_key=_env("BRAVE_API_KEY"),
            firecrawl_api_key=_env("FIRECRAWL_API_KEY"),
            github_token=_env("GITHUB_TOKEN"),
            github_mcp_url=_env("GITHUB_MCP_URL") or DEFAULT_GITHUB_MCP_URL,
        )

    @property
    def search_provider(self) -> str:
        if self.brave_api_key:
            return "brave"
        if self.firecrawl_api_key:
            return "firecrawl"
        return "duckduckgo"
