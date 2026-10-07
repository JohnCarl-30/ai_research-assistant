# Scout: company research for Claude

Company research for Claude that runs on your own computer and needs **no API
keys and no accounts**. Ask about any company and Scout builds a dossier from
public sources:

- **Facts** from Wikidata: website, founding year, headcount, headquarters, industry
- **Tech stack** the company's website runs on (framework, hosting, analytics, support tools)
- **Email and SaaS tools** from the domain's public DNS records
- **Hiring** from its public job board (Greenhouse, Lever, Ashby, Workable,
  SmartRecruiters, Recruitee or Personio): open roles by
  team and location, remote share, and the technologies the job posts mention
- **Engineering** from its GitHub organisation: languages, frameworks, activity
- **Hacker News** discussions of its launches and blog posts
- **Your saved notes** about it
- **What changed** since you last looked: hiring rising or falling, teams that
  started or stopped hiring, new technologies in job posts, GitHub going quiet

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
- `/scout:watchlist`: what changed at the companies you follow
- Or just ask: "what does Vercel build with?" Claude picks the skill up itself.

## Install in Claude Desktop

1. Download `scout-<version>.mcpb` from the repository's Releases page.
2. Double-click it, or drag it into **Settings → Extensions**.
3. Settings: where to keep your notes (default `~/.scout`) and an optional
   GitHub token. Neither is needed.

Turn on Claude's web search too: Scout covers structured sources and leaves news
and reviews to it. In Claude Desktop you can also start from the **+** menu:
**Research a company**, **Compare companies**, **Check my watchlist**,
**Research a topic**. Your notes are attachable from the same menu.

## Tools

| Tool | What it does |
|---|---|
| `research_company` | The dossier above, in one call, with progress updates. Pass `domain=` when you know the website |
| `what_changed` | Research again and compare with the last time (an earlier day) |
| `watch_company` / `unwatch_company` / `list_watchlist` | Companies to follow (up to 25) |
| `check_watchlist` | What changed at every watched company |
| `read_page` | A public web page as plain text. Private and local network addresses are refused |
| `github_research` | A company's GitHub org on its own: languages, frameworks, repos, activity |
| `save_note` / `search_notes` / `list_notes` / `get_note` | Your local research notebook (search ranks by BM25) |
| `delete_note` | Delete a note (marked destructive, so clients can ask you first) |
| `export_notes` | Every note as a Markdown file, e.g. into an Obsidian vault |

Every tool declares its output schema and returns structured results, and
notes are also readable as resources (`scout://notes`, `scout://notes/<id>`).

## Memory

Each dossier leaves a small snapshot of its signals in `history.db`: open roles
by team, technologies in job posts and on the website, GitHub activity, Hacker
News stories and headcount, at most one per company per day. The next dossier is
compared with the latest snapshot from an earlier day and says what changed in
`since_last_time`, which no web search can tell you. A section Scout couldn't
reach this time is never reported as "gone".

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

- **GitHub without a token:** Scout uses only GitHub's search API (10 searches a
  minute) and reads files from `raw.githubusercontent.com`, which doesn't count
  against GitHub's API quota. A company takes 1 to 4 searches, so you can research
  several companies a minute, and results are cached for a day. If the search
  limit runs out, Scout waits for it to reset (at most a minute) and tries
  once more, so a quick run of companies is slower rather than incomplete. An optional
  GitHub token in Scout's settings (read-only, public repositories) raises the
  search limit to 30 a minute. It is stored as a secret by Claude, and Scout
  never reads tokens you set in your shell for other tools.
- **Small private companies** are often missing from Wikidata and may not use a
  public job board. The dossier will be thinner, and its `gaps` say where.
- **DNS and website signals** show what a company has set up, not necessarily
  what it uses today.

## Privacy

Notes, research snapshots, the watchlist and a response cache are stored only
in your notes folder (`notes.db`, `history.db`, `cache.db`). Scout contacts only these public services, and only to research the
company you asked about: `wikidata.org`, the company's own website, your normal
DNS resolver, `hn.algolia.com`, `api.github.com` and `raw.githubusercontent.com`,
and the job board APIs
(`boards-api.greenhouse.io`, `api.lever.co`, `api.ashbyhq.com`, `apply.workable.com`,
`api.smartrecruiters.com`, `<company>.recruitee.com`, `<company>.jobs.personio.de`). There are no
accounts, keys or telemetry. Requests identify Scout by a User-Agent naming the
project (Wikimedia requires one with contact details); nothing about you is sent.

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

To release, set the new version everywhere it's recorded and note the changes:

```bash
uv run python scripts/bump_extension_version.py 0.3.0   # from the repo root
```

It also renames the CHANGELOG's **Unreleased** section to `0.3.0`; that section
becomes the release notes.

After that's merged, push a tag `vX.Y.Z`, or run **Release extension** on `main`
with **publish** ticked. The workflow tests, validates, packs `scout-X.Y.Z.mcpb`
and attaches it to a GitHub Release.

Signing the bundle and listing Scout in Anthropic's plugin directory are
described in [PUBLISHING.md](../PUBLISHING.md).

`tests/test_packaging.py` keeps the Desktop manifest, the plugin manifest and the
marketplace in step: the same version, settings and tool names.

### Other MCP clients

It is a standard stdio MCP server, so any MCP client can run it:
`uv run --directory /path/to/extension python -m scout_mcp`, optionally with
`SCOUT_DATA_DIR` and `SCOUT_GITHUB_TOKEN` in the environment.

### Accuracy eval

`evals/companies.json` lists real companies with known answers (website,
Wikidata entry, GitHub org, job board, technologies), each marked as verified
or believed. `evals/run_eval.py` runs Scout against them and reports accuracy
per field, with a confidently wrong GitHub match counted as **critical**:

```bash
uv run python extension/evals/run_eval.py                  # live, keyless
uv run python extension/evals/run_eval.py --record tape/   # live, saving responses
uv run python extension/evals/run_eval.py --replay tape/   # offline replay
```

The `Extension accuracy eval` workflow runs it on GitHub Actions for pull
requests that touch the extension's code or the eval, and on demand. The report
appears on the run's summary page. Real companies change websites and job
boards, so a mismatch is either a bug or a stale answer: check which before
changing the code or the answer.
