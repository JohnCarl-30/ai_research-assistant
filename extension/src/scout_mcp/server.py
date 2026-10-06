"""Scout MCP server: company research, plus the web, GitHub and notes tools behind it."""

from functools import cache, partial

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from scout_mcp import company as company_mod
from scout_mcp import web
from scout_mcp.config import Config
from scout_mcp.github import open_github, research_github
from scout_mcp.notes import Notebook

INSTRUCTIONS = """\
Scout researches companies. For any question about a company, start with
research_company: it returns one dossier (website, news, engineering, culture,
GitHub tech stack, and the user's saved notes). Then read_page the sources that
matter for the question, and web_search for anything the dossier lacks. Cite
the URLs you used. Save findings worth keeping with save_note (source URL and a
few tags, including the company name). Notes stay on the user's computer."""

KEYLESS_SEARCH_HINT = (
    "Search is using the free DuckDuckGo fallback, which blocks automated queries at "
    "times. Adding a Brave Search API key (free tier) in the Scout extension settings "
    "makes search reliable."
)

READ_ONLY_WEB = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
READ_ONLY_LOCAL = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


def create_server(config: Config) -> FastMCP:
    mcp = FastMCP("scout", instructions=INSTRUCTIONS)

    @cache
    def notebook() -> Notebook:
        return Notebook(config.data_dir / "notes.db")

    # --- Company research -----------------------------------------------------

    @mcp.tool(annotations=READ_ONLY_WEB)
    async def research_company(company: str, domain: str | None = None) -> dict:
        """Research a company in one call and return a dossier to analyse.

        Gathers: the company's homepage, search results on what it does, recent
        news (funding, launches, layoffs), engineering (blog, tech stack) and
        culture (careers, reviews), its public GitHub organisation, and notes the
        user saved before. "gaps" lists what could not be found. Search results
        are snippets: read_page the important ones before drawing conclusions.

        Args:
            company: Company name, e.g. "Linear".
            domain: The company's website, e.g. "linear.app". Found automatically
                when omitted, but giving it makes GitHub matching more reliable.
        """
        github = (
            partial(open_github, config.github_token, config.github_mcp_url)
            if config.github_token
            else None
        )
        dossier = await company_mod.research_company(
            company,
            domain=domain,
            search=partial(
                _search_only,
                brave_api_key=config.brave_api_key,
                firecrawl_api_key=config.firecrawl_api_key,
            ),
            read=partial(web.read_page, firecrawl_api_key=config.firecrawl_api_key),
            open_github=github,
            notebook=notebook(),
        )
        if config.search_provider == "duckduckgo" and any(
            "search failed" in gap for gap in dossier.gaps
        ):
            dossier.gaps.append(KEYLESS_SEARCH_HINT)
        return dossier.to_dict()

    # --- Web ------------------------------------------------------------------

    @mcp.tool(annotations=READ_ONLY_WEB)
    async def web_search(query: str, max_results: int = 8) -> dict:
        """Search the web. Returns titles, URLs and snippets; use read_page for full text.

        Args:
            query: What to search for. Search operators like site: work with most providers.
            max_results: Number of results, 1-20.
        """
        try:
            provider, results = await web.search(
                query,
                max_results,
                brave_api_key=config.brave_api_key,
                firecrawl_api_key=config.firecrawl_api_key,
            )
        except Exception as e:
            hint = ""
            if config.search_provider == "duckduckgo":
                hint = f" {KEYLESS_SEARCH_HINT}"
            raise ToolError(f"Search failed ({config.search_provider}): {e}.{hint}") from e
        return {"provider": provider, "results": [r.to_dict() for r in results]}

    @mcp.tool(annotations=READ_ONLY_WEB)
    async def read_page(url: str, max_chars: int = 20_000) -> dict:
        """Read a public web page as plain text (title, final URL, text).

        Args:
            url: An http(s) URL. Private and local network addresses are refused.
            max_chars: Maximum characters of text to return, 500-100000.
        """
        try:
            page = await web.read_page(url, max_chars, firecrawl_api_key=config.firecrawl_api_key)
        except web.BlockedURLError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Could not read {url}: {e}") from e
        return page.to_dict()

    @mcp.tool(annotations=READ_ONLY_WEB)
    async def github_research(company: str, domain: str | None = None) -> dict:
        """What a company builds, from its public GitHub organisation.

        Finds the org and reports top languages, frameworks from dependency
        manifests, notable repos and last activity, with a match confidence.
        A "low" confidence org was guessed from the name and may be a different
        company: check its repos fit before relying on it.

        Args:
            company: Company name, e.g. "Stripe".
            domain: The company's website domain, e.g. "stripe.com". Improves matching.
        """
        if not config.github_token:
            raise ToolError(
                "GitHub research needs a GitHub token. Add one in the Scout extension "
                "settings (a fine-grained token with public repository read access)."
            )
        async with open_github(config.github_token, config.github_mcp_url) as call:
            if call is None:
                raise ToolError("Could not connect to GitHub. Check the token and connection.")
            profile = await research_github(company, call, domain=domain)
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
2. web_search from two or three different angles, then read_page the most
   relevant and credible sources (aim for at least three independent ones).
3. Write a clear summary: key facts, where sources disagree, and what is
   still uncertain. Cite each claim with its URL.
4. save_note the summary with its main source URLs and a few tags."""

    @mcp.prompt(title="Research a company")
    def company_research(company: str, domain: str = "") -> str:
        """Company brief for a job seeker: what it does, tech stack, culture, red flags."""
        domain_arg = f', domain="{domain}"' if domain else ""
        return f"""Research the company {company} for me as a job seeker.

1. Call research_company(company="{company}"{domain_arg}).
2. read_page the most informative sources it found: the homepage or about
   page, the most recent news, and the engineering blog or careers page.
3. Write a brief with these sections, citing a URL for every claim:
   - What they do: products, customers, business model
   - Size and stage: headcount, funding, growth signals
   - Tech stack: from the GitHub evidence and engineering posts. Say if the
     GitHub match confidence is "low"
   - Culture: how they work, what employees say
   - Red flags: layoffs, bad reviews, stale GitHub, funding trouble
   - Questions to ask in an interview
   Say plainly what you could not find (see "gaps").
4. save_note the brief, tagged "{company.lower()}" and "company"."""

    @mcp.prompt(title="Compare companies")
    def compare_companies(companies: str) -> str:
        """Side-by-side comparison of several companies (comma-separated names)."""
        names = [c.strip() for c in companies.split(",") if c.strip()]
        listed = ", ".join(names)
        return f"""Compare these companies for me as a job seeker: {listed}.

1. Call research_company for each one.
2. read_page the key sources for each where the snippets are not enough.
3. Give a comparison table (what they do, stage and size, tech stack, culture
   signals, red flags), then a short recommendation of which fits someone who
   values growth, stability or interesting engineering. Cite sources.
4. save_note the comparison tagged "comparison" plus each company name."""

    return mcp


async def _search_only(
    query: str, limit: int, *, brave_api_key: str | None, firecrawl_api_key: str | None
) -> list[web.SearchResult]:
    _, results = await web.search(
        query, limit, brave_api_key=brave_api_key, firecrawl_api_key=firecrawl_api_key
    )
    return results


def main() -> None:
    create_server(Config.from_env()).run()
