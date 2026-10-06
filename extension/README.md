# Scout: company research for Claude

Company research for Claude that runs on your own computer. Ask about any
company and Scout gathers a dossier: its website, recent news, engineering and
culture sources, its real tech stack from GitHub, and what you saved before.
Claude writes a cited brief and keeps it in a notebook stored on your machine.

The same folder is both a **Claude Desktop extension** and a **Claude Code
plugin**. Both share one notebook (`~/.scout` by default).

## Install in Claude Code

```
/plugin marketplace add <owner>/ai_research-assistant
/plugin install scout@scout-plugins
```

Replace `<owner>` with the GitHub account or organisation that hosts this
repository.

Then add your keys with `/plugin configure scout@scout-plugins`. They're all
optional, but add a Brave Search key (see the table below). Claude Code installs
Python and the dependencies itself; you only need
[uv](https://docs.astral.sh/uv/) on your PATH.

Use it:

- `/scout:research-company Linear linear.app`: a full cited brief
- `/scout:compare-companies Stripe, Adyen`: a side-by-side comparison
- Or just ask: "what does Vercel build with?" Claude picks the skill up itself.

## Install in Claude Desktop

1. Download `scout.mcpb` (see [Building](#building) to make it yourself).
2. Double-click it, or in Claude Desktop open **Settings → Extensions** and
   drag the file in.
3. Fill in the settings form. Every field is optional:

| Setting | What it unlocks | Where to get it |
|---|---|---|
| Brave Search API key | Reliable web search (strongly recommended) | [brave.com/search/api](https://brave.com/search/api/), free tier available |
| Firecrawl API key | Search, plus reading JavaScript-heavy pages | [firecrawl.dev](https://firecrawl.dev) |
| GitHub token | `github_research` | GitHub → Settings → Developer settings → Fine-grained tokens, with public repository read access only |
| Notes folder | Where the notebook is stored | Defaults to `~/.scout` |

**Add a Brave Search key.** Without any key, search falls back to DuckDuckGo,
which sometimes answers automated searches with a CAPTCHA instead of results.
When that happens Scout says so instead of returning nothing, but research will
be thin until you add a key. Brave's free tier is enough for personal use. Claude Desktop installs Python and the dependencies
for you, so the first launch takes a few seconds longer.

## Use

Just ask, for example:

- "Research the current state of solid-state batteries."
- "What does Linear's engineering team build with? Save what you find."
- "What have I saved about vector databases?"

In Claude Desktop, you can also start from a prompt in the **+** menu:

- **Research a topic**: multi-source research with citations, saved as a note.
- **Research a company**: mission, tech stack (with GitHub evidence), culture,
  red flags and interview questions.

## Tools

| Tool | What it does |
|---|---|
| `web_search` | Web search via Brave, Firecrawl or DuckDuckGo, whichever is configured first |
| `read_page` | A public web page as plain text. Private and local network addresses are refused |
| `github_research` | A company's GitHub org: languages, frameworks, notable repos, last activity |
| `save_note` | Save a finding (markdown, source URL, tags) |
| `search_notes` | Keyword search over saved notes (BM25, with snippets) |
| `list_notes` / `get_note` | Browse and read saved notes |
| `delete_note` | Delete a note (marked destructive, so clients can ask you first) |

## Privacy

- Notes are stored only in a SQLite file in your notes folder (`notes.db`).
- Search queries go to the search provider you configured. Page reads go to
  the page's own site, or to Firecrawl if you added a key.
- `github_research` uses GitHub's MCP server in read-only mode, and your
  token is sent only to GitHub.
- Your API keys are kept in your operating system's keychain by Claude Desktop.

## Building

You need [uv](https://docs.astral.sh/uv/) and Node.js.

```bash
cd extension
uv run pytest                      # tests, offline
npx @anthropic-ai/mcpb validate manifest.json
npx @anthropic-ai/mcpb pack . scout.mcpb
```

To try it with the MCP Inspector without installing it:

```bash
npx @modelcontextprotocol/inspector uv run --directory . python -m scout_mcp
```

To check the Claude Code plugin and install it from your local checkout:

```bash
claude plugin validate . --strict                 # the plugin (this folder)
claude plugin validate .. --strict                # the marketplace (repo root)
claude plugin marketplace add /path/to/ai_research-assistant
claude plugin install scout@scout-plugins
```

`tests/test_packaging.py` keeps the Desktop manifest, the plugin manifest and
the marketplace in step: the same version, settings and tool names.

### Other MCP clients

It is a standard stdio MCP server, so any MCP client can run it:
`uv run --directory /path/to/extension python -m scout_mcp`, with the keys in
the environment (`BRAVE_API_KEY`, `FIRECRAWL_API_KEY`, `GITHUB_TOKEN`,
`SCOUT_DATA_DIR`).
