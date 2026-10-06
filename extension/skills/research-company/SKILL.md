---
name: research-company
description: Research a company and write a cited brief (what it does, size and stage, tech stack, hiring, culture, red flags, interview questions). Use when the user asks about a company, e.g. "research Stripe", "what does Linear build with", "is Vercel hiring", "I have an interview at <company>", "tell me about <company>".
argument-hint: <company> [website domain]
allowed-tools: WebSearch WebFetch mcp__plugin_scout_scout__research_company mcp__plugin_scout_scout__read_page mcp__plugin_scout_scout__github_research mcp__plugin_scout_scout__search_notes mcp__plugin_scout_scout__save_note
---

# Research a company

Company to research: $ARGUMENTS

If a website domain was given after the name (e.g. `Linear linear.app`), use
it. If no company was given, ask which one.

1. If you don't know the company's official website, find it with WebSearch.
   Then call `research_company` with the name and `domain`. The domain makes
   every part of the dossier more exact; without it, only an unambiguous
   Wikidata match can find the site.
2. The dossier has no news in it. Use WebSearch for recent news, funding and
   employee reviews, and `read_page` (or WebFetch) the most informative sources.
3. Write a brief with these sections, citing a URL for every claim:
   - What they do: products, customers, business model
   - Size and stage: headcount, founding year, funding, growth signals
   - Tech stack: from the website fingerprint, job posts and GitHub. Say if the
     GitHub match confidence is "low"
   - Hiring: open roles by team and location, remote share
   - Culture: how they work, what employees say
   - Red flags: layoffs, bad reviews, stale GitHub, hiring freeze
   - Questions to ask in an interview
   Say plainly what you could not find (see `gaps`). If `gaps` says GitHub's
   rate limit is used up, mention that GitHub details can be retried in an hour.
4. `save_note` the brief, tagged with the company name in lowercase and
   `company`, so it turns up in later research.
