"""The server end to end, through a real MCP client session in memory."""

import json
from pathlib import Path

from fakes import FakeFetcher, fixture
from mcp.shared.memory import create_connected_server_and_client_session

from scout_mcp.config import Config
from scout_mcp.server import create_server
from scout_mcp.sources import dnsinfo

MANIFEST = json.loads((Path(__file__).parents[1] / "manifest.json").read_text())


def _config(tmp_path):
    return Config(data_dir=tmp_path)


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


async def test_blocked_urls_are_explained(tmp_path):
    async with create_connected_server_and_client_session(create_server(_config(tmp_path))) as c:
        local = await c.call_tool("read_page", {"url": "http://127.0.0.1:8080/"})
    assert local.isError and "not a public address" in local.content[0].text


async def test_research_company_through_mcp_with_no_keys(tmp_path, monkeypatch):
    async def no_dns(domain):
        return dnsinfo.DnsInfo(email_provider=["Google Workspace"])

    monkeypatch.setattr(dnsinfo, "lookup", no_dns)
    fetcher = FakeFetcher({
        "list=search": json.dumps({"query": {"search": [{"title": "Q7624104"}]}}),
        "sparql": fixture("wikidata_sparql.json"),
        "api.github.com": (403, "API rate limit exceeded"),
    })
    server = create_server(_config(tmp_path), fetcher=fetcher)
    async with create_connected_server_and_client_session(server) as c:
        result = await c.call_tool("research_company", {"company": "Stripe",
                                                         "domain": "stripe.com"})
    dossier = json.loads(result.content[0].text)
    assert not result.isError
    assert dossier["facts"]["employees"] == 8000
    assert dossier["dns"]["email_provider"] == ["Google Workspace"]
    assert any("60 an hour" in gap for gap in dossier["gaps"])


async def test_company_prompt_drives_the_dossier_tool(tmp_path):
    async with create_connected_server_and_client_session(create_server(_config(tmp_path))) as c:
        prompt = await c.get_prompt("company_research", {"company": "Linear",
                                                         "domain": "linear.app"})
    text = prompt.messages[0].content.text
    assert 'research_company(company="Linear", domain="linear.app")' in text
    assert "web search" in text  # Scout itself does not search


def test_blank_install_form_fields_mean_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("SCOUT_DATA_DIR", "${user_config.notes_directory}")
    monkeypatch.setenv("GITHUB_TOKEN", "")
    config = Config.from_env()
    assert config.github_token is None
    assert config.data_dir == Path.home() / ".scout"
