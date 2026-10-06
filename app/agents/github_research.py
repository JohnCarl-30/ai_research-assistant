"""GitHub research for the backend, configured from Settings.

The implementation lives in ``scout_mcp.github`` (extension/), shared with the
desktop extension.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from scout_mcp.github import GitHubProfile, ToolCaller, open_github, research_github

from app.config import Settings, get_settings

__all__ = ["GitHubProfile", "ToolCaller", "open_github_research", "research_github"]


@asynccontextmanager
async def open_github_research(
    settings: Settings | None = None,
) -> AsyncIterator[ToolCaller | None]:
    """A GitHub ToolCaller from Settings, or None when unavailable."""
    settings = settings or get_settings()
    async with open_github(settings.github_token, settings.github_mcp_url) as call:
        yield call
