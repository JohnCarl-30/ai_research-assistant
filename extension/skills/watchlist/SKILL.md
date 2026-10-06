---
name: watchlist
description: Follow companies over time and report what changed at them (hiring rising or falling, teams starting or stopping hiring, new technologies, GitHub going quiet, news). Use when the user says "watch <company>", "stop watching <company>", "what's new at the companies I follow", "check my watchlist", or "what changed at <company>".
argument-hint: [add <company> [domain] | remove <company> | check]
allowed-tools: WebSearch WebFetch mcp__plugin_scout_scout__watch_company mcp__plugin_scout_scout__unwatch_company mcp__plugin_scout_scout__list_watchlist mcp__plugin_scout_scout__check_watchlist mcp__plugin_scout_scout__what_changed mcp__plugin_scout_scout__read_page mcp__plugin_scout_scout__save_note
---

# Watchlist

Request: $ARGUMENTS

- **add**: find the company's official website with WebSearch if you don't
  know it, then call `watch_company` with `domain`. Always pass the domain, so
  every check looks at the same company.
- **remove**: call `unwatch_company`.
- **One company** ("what changed at X"): call `what_changed` with its domain.
- **check**, or no arguments: call `check_watchlist` (it takes 10 to 30 seconds
  a company). If the watchlist is empty, say how to add a company.

When reporting changes:

1. Lead with the companies where something significant changed: open roles
   falling sharply, a team that stopped hiring, a new team hiring, GitHub gone
   quiet. For each, use WebSearch to find out why (layoffs, funding, a new
   product) and cite what you find.
2. Give the companies where nothing notable changed one line each.
3. A company researched for the first time has no comparison yet; say the
   next check will show changes.
4. `save_note` a short summary tagged `watchlist`.
