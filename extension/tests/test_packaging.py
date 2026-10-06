"""The Claude Desktop bundle and the Claude Code plugin describe the same server."""

import json
import re
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from scout_mcp import __version__
from scout_mcp.config import Config
from scout_mcp.server import create_server

ROOT = Path(__file__).parents[1]
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
PLUGIN = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
MARKETPLACE = json.loads((ROOT.parent / ".claude-plugin" / "marketplace.json").read_text())


def test_versions_agree():
    assert MANIFEST["version"] == PLUGIN["version"] == __version__


def test_plugin_passes_the_same_settings_as_the_desktop_bundle():
    desktop_env = MANIFEST["server"]["mcp_config"]["env"]
    plugin_env = PLUGIN["mcpServers"]["scout"]["env"]
    assert {k: v for k, v in plugin_env.items() if k != "UV_PROJECT_ENVIRONMENT"} == desktop_env
    assert set(PLUGIN["userConfig"]) == set(MANIFEST["user_config"])


def test_marketplace_points_at_this_plugin():
    (entry,) = MARKETPLACE["plugins"]
    assert entry["name"] == PLUGIN["name"]
    assert (ROOT.parent / entry["source"]).resolve() == ROOT


async def test_skills_only_preapprove_real_read_or_note_tools(tmp_path):
    config = Config(data_dir=tmp_path, brave_api_key=None, firecrawl_api_key=None,
                    github_token=None, github_mcp_url="https://example.invalid/mcp/")
    async with create_connected_server_and_client_session(create_server(config)) as client:
        tools = {t.name for t in (await client.list_tools()).tools}

    prefix = f"mcp__plugin_{PLUGIN['name']}_scout__"
    for skill in (ROOT / "skills").glob("*/SKILL.md"):
        frontmatter = skill.read_text().split("---")[1]
        allowed = re.search(r"^allowed-tools:(.*)$", frontmatter, re.M).group(1).split()
        names = {a.removeprefix(prefix) for a in allowed}
        assert all(a.startswith(prefix) for a in allowed), skill
        assert names <= tools, f"{skill}: unknown tools {names - tools}"
        assert "delete_note" not in names, f"{skill} must not pre-approve deletion"
