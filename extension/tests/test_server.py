"""The server end to end, through a real MCP client session in memory."""

import json
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from scout_mcp.config import Config
from scout_mcp.server import create_server

MANIFEST = json.loads((Path(__file__).parents[1] / "manifest.json").read_text())


def _config(tmp_path, **overrides):
    values = dict(data_dir=tmp_path, brave_api_key=None, firecrawl_api_key=None,
                  github_token=None, github_mcp_url="https://example.invalid/mcp/")
    return Config(**(values | overrides))


async def test_manifest_lists_exactly_the_servers_tools(tmp_path):
    async with create_connected_server_and_client_session(create_server(_config(tmp_path))) as c:
        tools = (await c.list_tools()).tools
        prompts = (await c.list_prompts()).prompts
    assert {t.name for t in tools} == {t["name"] for t in MANIFEST["tools"]}
    assert {p.name for p in prompts} == {"research", "company_research", "compare_companies"}
    annotations = {t.name: t.annotations for t in tools}
    assert annotations["delete_note"].destructiveHint is True
    assert annotations["research_company"].readOnlyHint is True


async def test_notes_round_trip_through_mcp(tmp_path):
    async with create_connected_server_and_client_session(create_server(_config(tmp_path))) as c:
        saved = await c.call_tool("save_note", {"title": "Acme", "content": "Uses Rust.",
                                                "tags": ["acme"]})
        note_id = json.loads(saved.content[0].text)["id"]
        found = await c.call_tool("search_notes", {"query": "rust"})
        missing = await c.call_tool("get_note", {"note_id": 999})

    assert json.loads(found.content[0].text)["results"][0]["id"] == note_id
    assert missing.isError
    assert (tmp_path / "notes.db").exists()


async def test_tools_explain_missing_configuration_and_blocked_urls(tmp_path):
    async with create_connected_server_and_client_session(create_server(_config(tmp_path))) as c:
        gh = await c.call_tool("github_research", {"company": "Acme"})
        local = await c.call_tool("read_page", {"url": "http://127.0.0.1:8080/"})
    assert gh.isError and "GitHub token" in gh.content[0].text
    assert local.isError and "not a public address" in local.content[0].text


async def test_company_prompt_drives_the_dossier_tool(tmp_path):
    async with create_connected_server_and_client_session(create_server(_config(tmp_path))) as c:
        prompt = await c.get_prompt("company_research", {"company": "Linear",
                                                         "domain": "linear.app"})
    text = prompt.messages[0].content.text
    assert 'research_company(company="Linear", domain="linear.app")' in text


def test_blank_install_form_fields_mean_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAVE_API_KEY", "")
    monkeypatch.setenv("GITHUB_TOKEN", "${user_config.github_token}")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    config = Config.from_env()
    assert config.brave_api_key is None and config.github_token is None
    assert config.search_provider == "duckduckgo"
    assert config.data_dir == tmp_path
