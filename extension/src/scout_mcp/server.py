"""Scout MCP server: keyless company research, page reading and a local notebook."""

from functools import cache

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from scout_mcp import company as company_mod
from scout_mcp import web
from scout_mcp.config import Config
from scout_mcp.github import research_github
from scout_mcp.notes import Notebook
from scout_mcp.sources.github_rest import GitHubRateLimitError, github_rest_caller
from scout_mcp.sources.http import Cache, Fetcher

INSTRUCTIONS = """\
Scout researches companies from public sources, with no API keys. For any
question about a company, start with research_company. It returns one dossier:
Wikidata facts, the website's tech stack and links, email and SaaS tools from
DNS, hiring from public job boards, the GitHub organisation, Hacker News
stories, and the user's saved notes. Pass domain= when you know the company's
website. Scout does not search the web: use your own web search for news,
funding and employee reviews, and read_page to read a source in full. Cite the
URLs you used. Save findings worth keeping with save_note (source URL and a few
tags, including the company name). Notes stay on the user's computer."""

READ_ONLY_WEB = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
READ_ONLY_LOCAL = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


def create_server(config: Config, fetcher: Fetcher | None = None) -> FastMCP:
    mcp = FastMCP("scout", instructions=INSTRUCTIONS)

    @cache
    def notebook() -> Notebook:
        return Notebook(config.data_dir / "notes.db")

    @cache
    def http() -> Fetcher:
        return fetcher or Fetcher(Cache(config.data_dir / "cache.db"))

    # --- Company research -----------------------------------------------------

    @mcp.tool(annotations=READ_ONLY_WEB)
    async def research_company(company: str, domain: str | None = None) -> dict:
        """Research a company from public sources and return a dossier to analyse.

        Sections: facts (Wikidata: website, founded, headcount, HQ, industry),
        website (tech stack fingerprint, about text, social links), dns (email
        provider and SaaS tools), hiring (open roles by team and location, remote
        share, technologies named in job posts), github (languages, frameworks,
        activity), hacker_news (stories linking to the site), saved_notes, gaps
        (what could not be found) and next_steps. It does not search the web.

        Args:
            company: Company name, e.g. "Linear".
            domain: The company's website, e.g. "linear.app". Strongly recommended:
                without it, only an unambiguous Wikidata name match can find the site.
        """
        dossier = await company_mod.research_company(
            company,
            domain=domain,
            fetcher=http(),
            notebook=notebook(),
            github_token=config.github_token,
        )
        return dossier.to_dict()

    # --- Web ------------------------------------------------------------------

    @mcp.tool(annotations=READ_ONLY_WEB)
    async def read_page(url: str, max_chars: int = 20_000) -> dict:
        """Read a public web page as plain text (title, final URL, text).

        Args:
            url: An http(s) URL. Private and local network addresses are refused.
            max_chars: Maximum characters of text to return, 500-100000.
        """
        try:
            page = await web.read_page(url, max_chars)
        except web.BlockedURLError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Could not read {url}: {e}") from e
        return page.to_dict()

    @mcp.tool(annotations=READ_ONLY_WEB)
    async def github_research(
        company: str, domain: str | None = None, org: str | None = None
    ) -> dict:
        """What a company builds, from its public GitHub organisation.

        Reports top languages, frameworks from dependency manifests, notable
        repos and last activity, with a match confidence. A "low" confidence org
        was guessed from the name and may be a different company. Uses GitHub's
        public search API and raw files without a token (results cached a day).

        Args:
            company: Company name, e.g. "Stripe".
            domain: The company's website, e.g. "stripe.com". Improves matching.
            org: The exact GitHub organisation login, if known.
        """
        try:
            profile = await research_github(
                company, github_rest_caller(http(), config.github_token), domain=domain, org=org
            )
        except GitHubRateLimitError as e:
            raise ToolError(str(e)) from e
        if profile is None:
            return {"found": False, "company": company}
        return {"found": True, **profile.to_dict()}

    # --- Notes ----------------------------------------------------------------

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
    def save_note(
        title: str, content: str, url: str | None = None, tags: list[str] | None = None
    ) -> dict:
        """Save a research finding to the user's local notebook.

        Args:
            title: Short, specific title.
            content: The finding, in markdown. Self-contained: it will be read later
                without this conversation.
            url: Source URL, if the note came from a page.
            tags: A few lowercase topic tags, e.g. ["stripe", "payments"].
        """
        return notebook().save(title, content, url=url, tags=tags).to_dict()

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    def search_notes(query: str, limit: int = 10) -> dict:
        """Search saved notes by keyword (best matches first, with highlighted snippets).

        Args:
            query: Words to look for in note titles, content and tags.
            limit: Maximum notes to return, 1-50.
        """
        hits = notebook().search(query, max(1, min(limit, 50)))
        return {
            "results": [
                {"id": n.id, "title": n.title, "url": n.url, "tags": n.tags, "snippet": snip}
                for n, snip in hits
            ]
        }

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    def list_notes(limit: int = 20, tag: str | None = None) -> dict:
        """Most recent saved notes, optionally only those with a tag.

        Args:
            limit: Maximum notes to return, 1-100.
            tag: Only notes carrying this tag.
        """
        notes = notebook().recent(max(1, min(limit, 100)), tag=tag)
        return {
            "notes": [
                {"id": n.id, "title": n.title, "url": n.url, "tags": n.tags,
                 "created_at": n.created_at}
                for n in notes
            ]
        }

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    def get_note(note_id: int) -> dict:
        """Full content of one saved note."""
        note = notebook().get(note_id)
        if note is None:
            raise ToolError(f"No note with id {note_id}")
        return note.to_dict()

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False))
    def delete_note(note_id: int) -> dict:
        """Permanently delete a saved note."""
        if not notebook().delete(note_id):
            raise ToolError(f"No note with id {note_id}")
        return {"deleted": note_id}

    # --- Prompts --------------------------------------------------------------

    @mcp.prompt(title="Research a topic")
    def research(topic: str) -> str:
        """Research any topic from multiple sources and save the findings."""
        return f"""Research this topic thoroughly: {topic}

1. search_notes for what I have already saved about it.
2. Use your own web search from two or three different angles, then read_page
   the most relevant and credible sources (at least three independent ones).
3. Write a clear summary: key facts, where sources disagree, and what is
   still uncertain. Cite each claim with its URL.
4. save_note the summary with its main source URLs and a few tags."""

    @mcp.prompt(title="Research a company")
    def company_research(company: str, domain: str = "") -> str:
        """Company brief for a job seeker: what it does, tech stack, hiring, culture, red flags."""
        domain_arg = f', domain="{domain}"' if domain else ""
        call = f'research_company(company="{company}"{domain_arg})'
        return f"""Research the company {company} for me as a job seeker.

{BRIEF_STEPS.format(call=call, tag=company.lower())}"""

    @mcp.prompt(title="Compare companies")
    def compare_companies(companies: str) -> str:
        """Side-by-side comparison of several companies (comma-separated names)."""
        names = [c.strip() for c in companies.split(",") if c.strip()]
        listed = ", ".join(names)
        return f"""Compare these companies for me as a job seeker: {listed}.

1. Call research_company for each one (find each website with your web search
   first if you don't know it, and pass it as domain=).
2. Use your web search for recent news and employee reviews of each.
3. Give a comparison table (what they do, stage and size, tech stack, hiring,
   culture signals, red flags), then a short recommendation of which fits
   someone who values growth, stability or interesting engineering. Cite
   sources, and say what you could not find for each company (its "gaps").
4. save_note the comparison tagged "comparison" plus each company name."""

    return mcp


BRIEF_STEPS = """\
1. If you don't know the company's official website, find it with your web
   search first. Then call {call} (adding domain= if you found the site).
2. Use your own web search for recent news, funding and employee reviews, and
   read_page the most informative sources. The dossier has no news in it.
3. Write a brief with these sections, citing a URL for every claim:
   - What they do: products, customers, business model
   - Size and stage: headcount, founding year, funding, growth signals
   - Tech stack: from the website fingerprint, job posts and GitHub. Say if the
     GitHub match confidence is "low"
   - Hiring: open roles by team and location, remote share
   - Culture: how they work, what employees say
   - Red flags: layoffs, bad reviews, stale GitHub, hiring freeze
   - Questions to ask in an interview
   Say plainly what you could not find (see "gaps").
4. save_note the brief, tagged "{tag}" and "company"."""


def main() -> None:
    create_server(Config.from_env()).run()
