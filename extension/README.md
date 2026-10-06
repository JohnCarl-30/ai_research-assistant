# Scout: company research for Claude

Company research for Claude that runs on your own computer and needs **no API
keys and no accounts**. Ask about any company and Scout builds a dossier from
public sources:

- **Facts** from Wikidata: website, founding year, headcount, headquarters, industry
- **Tech stack** the company's website runs on (framework, hosting, analytics, support tools)
- **Email and SaaS tools** from the domain's public DNS records
- **Hiring** from its public job board (Greenhouse, Lever or Ashby): open roles by
  team and location, remote share, and the technologies the job posts mention
- **Engineering** from its GitHub organisation: languages, frameworks, activity
- **Hacker News** discussions of its launches and blog posts
- **Your saved notes** about it

Claude adds recent news with its own web search, writes a cited brief, and saves
it to a notebook stored only on your machine.

The same folder is both a **Claude Code plugin** and a **Claude Desktop
extension**. Both share one notebook (`~/.scout` by default).

## Install in Claude Code

```
/plugin marketplace add <owner>/ai_research-assistant
/plugin install scout@scout-plugins
```

Replace `<owner>` with the GitHub account or organisation that hosts this
repository. You need [uv](https://docs.astral.sh/uv/) on your PATH; Claude Code
installs Python and the dependencies itself.

Use it:

- `/scout:research-company Linear linear.app`: a full cited brief
- `/scout:compare-companies Stripe, Adyen`: a side-by-side comparison
- Or just ask: "what does Vercel build with?" Claude picks the skill up itself.

## Install in Claude Desktop

1. Download `scout-<version>.mcpb` from the repository's Releases page.
2. Double-click it, or drag it into **Settings → Extensions**.
3. The only setting is where to keep your notes (default `~/.scout`).

Turn on Claude's web search too: Scout covers structured sources and leaves news
and reviews to it. In Claude Desktop you can also start from the **+** menu:
**Research a company**, **Compare companies**, **Research a topic**.

## Tools

| Tool | What it does |
|---|---|
| `research_company` | The dossier above, in one call. Pass `domain=` when you know the website |
| `read_page` | A public web page as plain text. Private and local network addresses are refused |
| `github_research` | A company's GitHub org on its own: languages, frameworks, repos, activity |
| `save_note` / `search_notes` / `list_notes` / `get_note` | Your local research notebook (search ranks by BM25) |
| `delete_note` | Delete a note (marked destructive, so clients can ask you first) |

## How it stays accurate without keys

- **Exact links beat guesses.** When the company's website links to its GitHub org
  or job board, or Wikidata records its GitHub account, Scout uses that exact
  account and marks the match `high` confidence. Only otherwise does it try
  name-based guesses, and it says so.
- **No name-only lookalikes.** Searching Wikidata for "Linear" finds a chipmaker
  and an insurer. Scout only accepts a name match when exactly one company has
  exactly that name; otherwise it asks for the domain.
- **Nothing silently missing.** Anything it can't find or reach is listed in
  `gaps`, so Claude can say what it doesn't know.

## Limits

- **GitHub allows 60 requests an hour without a token**, and one company uses
  about ten. Results are cached for a day. If you research many companies, set a
  `GITHUB_TOKEN` environment variable (read-only, public repositories) for
  5,000 an hour. In Claude Code, set it in the shell you start Claude from.
- **Small private companies** are often missing from Wikidata and may not use a
  public job board. The dossier will be thinner, and its `gaps` say where.
- **DNS and website signals** show what a company has set up, not necessarily
  what it uses today.

## Privacy

Notes and a response cache are stored only in your notes folder (`notes.db`,
`cache.db`). Scout contacts only these public services, and only to research the
company you asked about: `wikidata.org`, the company's own website, your normal
DNS resolver, `hn.algolia.com`, `api.github.com`, and the job board APIs
(`boards-api.greenhouse.io`, `api.lever.co`, `api.ashbyhq.com`). There are no
accounts, keys or telemetry.

## Building

You need [uv](https://docs.astral.sh/uv/) and Node.js.

```bash
cd extension
uv run pytest                                  # offline tests
npx @anthropic-ai/mcpb validate manifest.json  # Desktop manifest
npx @anthropic-ai/mcpb pack . scout.mcpb       # Desktop bundle
claude plugin validate . --strict              # Claude Code plugin (this folder)
claude plugin validate .. --strict             # the marketplace (repo root)
```

Releases are built by GitHub Actions: push a tag `vX.Y.Z` matching the version in
`manifest.json` and the workflow tests, validates, packs `scout.mcpb` and
attaches it to a GitHub Release.

`tests/test_packaging.py` keeps the Desktop manifest, the plugin manifest and the
marketplace in step: the same version, settings and tool names.

### Other MCP clients

It is a standard stdio MCP server, so any MCP client can run it:
`uv run --directory /path/to/extension python -m scout_mcp`, optionally with
`SCOUT_DATA_DIR` and `GITHUB_TOKEN` in the environment.
