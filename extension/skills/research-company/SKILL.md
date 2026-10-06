---
name: research-company
description: Research a company and write a cited brief (what it does, size and stage, tech stack from GitHub, culture, red flags, interview questions). Use when the user asks about a company, e.g. "research Stripe", "what does Linear build with", "I have an interview at Vercel", "is this company any good", "tell me about <company>".
argument-hint: <company> [website domain]
allowed-tools: mcp__plugin_scout_scout__research_company mcp__plugin_scout_scout__read_page mcp__plugin_scout_scout__web_search mcp__plugin_scout_scout__github_research mcp__plugin_scout_scout__search_notes mcp__plugin_scout_scout__save_note
---

# Research a company

Company to research: $ARGUMENTS

If a website domain was given after the name (e.g. `Linear linear.app`), pass
it as `domain`. If no company was given, ask which one.

1. Call `research_company` with the company name (and `domain` if known). It
   returns a dossier: homepage, search results for overview, news, engineering
   and culture, the GitHub organisation, notes saved before, and `gaps`.
2. `read_page` the most informative sources: the homepage or about page, the
   most recent news, and the engineering blog or careers page. Snippets alone
   are not enough to draw conclusions.
3. Write a brief with these sections, citing a URL for every claim:
   - What they do: products, customers, business model
   - Size and stage: headcount, funding, growth signals
   - Tech stack: from the GitHub evidence and engineering posts. Say if the
     GitHub match confidence is "low"
   - Culture: how they work, what employees say
   - Red flags: layoffs, bad reviews, stale GitHub, funding trouble
   - Questions to ask in an interview
   Say plainly what you could not find (see `gaps`). If `gaps` says search is
   on the DuckDuckGo fallback, tell the user to add a Brave Search key with
   `/plugin configure scout@scout-plugins`.
4. `save_note` the brief, tagged with the company name in lowercase and
   `company`, so it turns up in later research.
