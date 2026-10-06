# Changelog

All notable changes to Scout, the company research extension for Claude
Desktop and plugin for Claude Code.

## Unreleased

### Added
- Memory: every dossier says what changed since Scout last researched the
  company (`since_last_time`): open roles rising or falling, teams starting or
  stopping hiring, technologies appearing in job posts or on the website, GitHub
  going quiet, new Hacker News stories, headcount. New `what_changed` tool.
- Watchlist: `watch_company`, `unwatch_company`, `list_watchlist` and
  `check_watchlist`, a "Check my watchlist" prompt and a `/scout:watchlist`
  skill.
- Progress updates while a dossier is built.
- Every tool declares an output schema and returns structured results.
- Notes are readable as MCP resources, and `export_notes` writes them as
  Markdown files with front matter (e.g. into an Obsidian vault).
- Four more job boards: Workable, SmartRecruiters, Recruitee and Personio,
  common among European and smaller companies. Each is checked from links on
  the company's site and by name, all boards at once for each name.
- GitHub organisations are also found through GitHub's own record of an org's
  website, for orgs whose name can't be guessed (GitLab's is "gitlabhq").
- Weekly live accuracy eval that fails (and emails the repository owner) if
  accuracy drops below 90%, so a source that changes or blocks Scout is
  caught within a week.

### Fixed
- When a company and its product share a website on Wikidata (Tailscale,
  Hugging Face), the company's entry is used.

### Changed
- The accuracy eval covers 35 companies, now including smaller, European and
  non-tech ones (Mollie, Doctolib, Celonis, Pleo, Bosch, Patagonia, IKEA...).
- The optional GitHub token is now a setting in the install form, stored as a
  secret, instead of the `GITHUB_TOKEN` environment variable: Scout no longer
  reads credentials you set in your shell for other tools.
- The plugin starts its server with `uv run --locked`, so the locked
  dependency versions are always the ones installed.
- GitHub Actions moved to their Node 24 versions.

## 0.2.1 (2026-10-06)

### Fixed
- Wikidata facts work again: Scout's User-Agent now includes contact details,
  as Wikimedia requires.
- Job boards of large employers (Stripe, Cloudflare, Datadog, Palantir) are
  read; they were larger than the old 5 MB limit.
- Websites whose compressed responses httpx can't decode are retried
  uncompressed.
- "Join us on Discord" style links are no longer taken for careers pages.
- Wikidata facts are found under the subdomain a website redirects to
  (gitlab.com → about.gitlab.com).

### Changed
- GitHub research reads files from raw.githubusercontent.com and uses only the
  search API: about one API call per company instead of ten.

## 0.2.0 (2026-10-06)

### Changed
- No API keys needed. The dossier is built from keyless public sources:
  Wikidata, the company's website, DNS, public job boards (Greenhouse, Lever,
  Ashby), GitHub and Hacker News. Web search is left to Claude's own tool.

## 0.1.0 (2026-10-06)

### Added
- First release: company dossier, page reading, GitHub research and a local
  notebook, as a Claude Desktop extension and Claude Code plugin.
