"""The server end to end, through a real MCP client session in memory."""

import json
import sqlite3
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
    assert {p.name for p in prompts} == {"research", "company_research", "compare_companies",
                                         "watchlist_review"}
    annotations = {t.name: t.annotations for t in tools}
    assert annotations["delete_note"].destructiveHint is True
    assert annotations["list_watchlist"].readOnlyHint is True
    # Research records a snapshot locally, but never deletes or overwrites anything.
    assert annotations["research_company"].destructiveHint is False
    assert all(t.outputSchema for t in tools)


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
    assert any("without a token is used up" in gap for gap in dossier["gaps"])


async def test_company_prompt_drives_the_dossier_tool(tmp_path):
    async with create_connected_server_and_client_session(create_server(_config(tmp_path))) as c:
        prompt = await c.get_prompt("company_research", {"company": "Linear",
                                                         "domain": "linear.app"})
    text = prompt.messages[0].content.text
    assert 'research_company(company="Linear", domain="linear.app")' in text
    assert "web search" in text  # Scout itself does not search


def test_blank_install_form_fields_mean_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("SCOUT_DATA_DIR", "${user_config.notes_directory}")
    monkeypatch.setenv("SCOUT_GITHUB_TOKEN", "${user_config.github_token}")
    config = Config.from_env()
    assert config.github_token is None
    assert config.data_dir == Path.home() / ".scout"


def test_only_the_token_given_to_scout_is_used(monkeypatch):
    # A token the user set for other tools is not Scout's to send anywhere.
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_the_shell")
    monkeypatch.delenv("SCOUT_GITHUB_TOKEN", raising=False)
    assert Config.from_env().github_token is None
    monkeypatch.setenv("SCOUT_GITHUB_TOKEN", "github_pat_given")
    assert Config.from_env().github_token == "github_pat_given"


def _stripe_fetcher(employees: int = 8000) -> FakeFetcher:
    sparql = json.loads(fixture("wikidata_sparql.json"))
    for row in sparql["results"]["bindings"]:
        if "employees" in row:
            row["employees"]["value"] = str(employees)
    return FakeFetcher({
        "list=search": json.dumps({"query": {"search": [{"title": "Q7624104"}]}}),
        "sparql": json.dumps(sparql),
        "api.github.com": (403, "API rate limit exceeded"),
    })


async def test_research_is_structured_and_remembers_the_last_visit(tmp_path, monkeypatch):
    async def no_dns(domain):
        return dnsinfo.DnsInfo()

    monkeypatch.setattr(dnsinfo, "lookup", no_dns)
    server = create_server(_config(tmp_path), fetcher=_stripe_fetcher())
    async with create_connected_server_and_client_session(server) as c:
        first = await c.call_tool("research_company", {"company": "Stripe",
                                                        "domain": "stripe.com"})
    assert first.structuredContent["facts"]["employees"] == 8000
    assert first.structuredContent["since_last_time"]["previous_snapshot"] is None

    # Pretend that snapshot was taken a month ago, then look again.
    db = sqlite3.connect(tmp_path / "history.db")
    with db:
        db.execute("UPDATE snapshots SET day = '2026-01-01', taken_at = '2026-01-01T09:00:00'")
    db.close()
    server = create_server(_config(tmp_path), fetcher=_stripe_fetcher(employees=9000))
    async with create_connected_server_and_client_session(server) as c:
        changed = await c.call_tool("what_changed", {"company": "Stripe",
                                                     "domain": "stripe.com"})
    result = changed.structuredContent
    assert result["previous_snapshot"] == "2026-01-01"
    assert any("8000 to 9000" in change for change in result["changes"])


async def test_watchlist_through_mcp(tmp_path, monkeypatch):
    async def no_dns(domain):
        return dnsinfo.DnsInfo()

    monkeypatch.setattr(dnsinfo, "lookup", no_dns)
    server = create_server(_config(tmp_path), fetcher=_stripe_fetcher())
    async with create_connected_server_and_client_session(server) as c:
        await c.call_tool("watch_company", {"company": "Stripe", "domain": "stripe.com"})
        again = await c.call_tool("watch_company", {"company": "Stripe",
                                                    "domain": "stripe.com"})
        listed = await c.call_tool("list_watchlist", {})
        checked = await c.call_tool("check_watchlist", {})
        await c.call_tool("unwatch_company", {"company": "stripe"})
        after = await c.call_tool("list_watchlist", {})

    assert "Already" in again.structuredContent["note"]
    assert [w["domain"] for w in listed.structuredContent["companies"]] == ["stripe.com"]
    assert checked.structuredContent["checked"] == 1
    assert checked.structuredContent["results"][0]["company"] == "Stripe"
    assert after.structuredContent["companies"] == []


async def test_notes_are_resources_and_export_as_markdown(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "mine.md").write_text("untouched")
    async with create_connected_server_and_client_session(create_server(_config(tmp_path))) as c:
        saved = await c.call_tool("save_note", {"title": "Acme: stack", "content": "Uses Rust.",
                                                "url": "https://acme.example/blog",
                                                "tags": ["acme"]})
        note_id = saved.structuredContent["id"]
        index = await c.read_resource("scout://notes")
        one = await c.read_resource(f"scout://notes/{note_id}")
        exported = await c.call_tool("export_notes", {"folder": str(vault)})
        missing = await c.call_tool("export_notes", {"folder": str(tmp_path / "nope")})

    assert f"scout://notes/{note_id}" in index.contents[0].text
    assert one.contents[0].text.startswith("# Acme: stack")
    assert exported.structuredContent["written"] == 1
    text = (vault / exported.structuredContent["files"][0]).read_text()
    assert 'source: "https://acme.example/blog"' in text and "Uses Rust." in text
    assert (vault / "mine.md").read_text() == "untouched"
    assert missing.isError
