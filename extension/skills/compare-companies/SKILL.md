---
name: compare-companies
description: Compare several companies side by side for a job seeker (what they do, stage, tech stack, culture, red flags) and recommend which fits. Use when the user is choosing between companies or offers, e.g. "compare Stripe and Adyen", "which is better to work at, X or Y".
argument-hint: <company>, <company>[, ...]
allowed-tools: mcp__plugin_scout_scout__research_company mcp__plugin_scout_scout__read_page mcp__plugin_scout_scout__web_search mcp__plugin_scout_scout__github_research mcp__plugin_scout_scout__search_notes mcp__plugin_scout_scout__save_note
---

# Compare companies

Companies to compare: $ARGUMENTS

If fewer than two companies were given, ask for the rest.

1. Call `research_company` for each company.
2. `read_page` the key sources for each where the snippets are not enough.
3. Give a comparison table (what they do, stage and size, tech stack, culture
   signals, red flags), then a short recommendation of which fits someone who
   values growth, stability or interesting engineering. Cite sources, and say
   what you could not find for each company (its `gaps`).
4. `save_note` the comparison, tagged `comparison` plus each company name in
   lowercase.
