# Changelog

All notable changes to Scout, the company research extension for Claude
Desktop and plugin for Claude Code.

## Unreleased

### Added
- Weekly live accuracy eval that fails (and emails the repository owner) if
  accuracy drops below 90%, so a source that changes or blocks Scout is
  caught within a week.

### Changed
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
