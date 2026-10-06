"""Scout MCP server: keyless company research, memory of past research, and a
local notebook."""

from functools import cache
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from scout_mcp import company as company_mod
from scout_mcp import schemas, web
from scout_mcp.config import Config
from scout_mcp.github import research_github
from scout_mcp.memory import History
from scout_mcp.notes import Notebook
from scout_mcp.sources.github_rest import GitHubRateLimitError, github_rest_caller
from scout_mcp.sources.http import Cache, Fetcher

INSTRUCTIONS = """\
Scout researches companies from public sources, with no API keys, and
remembers past research. For any question about a company, start with
research_company. It returns one dossier: Wikidata facts, the website's tech
stack and links, email and SaaS tools from DNS, hiring from public job boards,
the GitHub organisation, Hacker News stories, the user's saved notes, and
since_last_time: what changed since Scout last looked. Pass domain= when you
know the company's website. Use what_changed when the user asks what's new at
a company, and the watchlist tools to follow companies over time. Scout does
not search the web: use your own web search for news, funding and employee
reviews, and read_page to read a source in full. Cite the URLs you used. Save
findings worth keeping with save_note (source URL and a few tags, including
the company name). Everything Scout stores stays on the user's computer."""

READ_ONLY_WEB = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
READ_ONLY_LOCAL = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
LOCAL_WRITE = ToolAnnotations(readOnlyHint=False, openWorldHint=False)
# Research also records a snapshot locally, so it isn't strictly read-only.
RESEARCH = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)

MAX_WATCHLIST = 25


def create_server(config: Config, fetcher: Fetcher | None = None) -> FastMCP:
    mcp = FastMCP("scout", instructions=INSTRUCTIONS)

    @cache
    def notebook() -> Notebook:
        return Notebook(config.data_dir / "notes.db")

    @cache
    def history() -> History:
        return History(config.data_dir / "history.db")

    @cache
    def http() -> Fetcher:
        return fetcher or Fetcher(Cache(config.data_dir / "cache.db"))

    async def dossier_for(company: str, domain: str | None, ctx: Context | None) -> dict:
        async def progress(step: int, message: str) -> None:
            if ctx is not None:
                await ctx.report_progress(step, 3, message)

        d = (await company_mod.research_company(
            company, domain=domain, fetcher=http(), notebook=notebook(),
            github_token=config.github_token, progress=progress,
        )).to_dict()
        d["since_last_time"] = history().record(d["company"], d["domain"], d).to_dict()
        return d

    def changes_of(d: dict) -> schemas.Changes:
        since = d["since_last_time"]
        return schemas.Changes(
            company=d["company"], domain=d["domain"],
            previous_snapshot=since["previous_snapshot"], changes=since["changes"],
            open_roles=(d.get("hiring") or {}).get("open_roles"), gaps=d["gaps"],
        )

    # --- Company research -----------------------------------------------------

    @mcp.tool(annotations=RESEARCH)
    async def research_company(
        company: str, domain: str | None = None, ctx: Context | None = None
    ) -> schemas.Dossier:
        """Research a company from public sources and return a dossier to analyse.

        Sections: facts (Wikidata: website, founded, headcount, HQ, industry),
        website (tech stack fingerprint, about text, social links), dns (email
        provider and SaaS tools), hiring (open roles by team and location, remote
        share, technologies named in job posts), github (languages, frameworks,
        activity), hacker_news (stories linking to the site), saved_notes,
        since_last_time (what changed since Scout last researched it), gaps (what
        could not be found) and next_steps. It does not search the web.

        Args:
            company: Company name, e.g. "Linear".
            domain: The company's website, e.g. "linear.app". Strongly recommended:
                without it, only an unambiguous Wikidata name match can find the site.
        """
        return schemas.Dossier(**await dossier_for(company, domain, ctx))

    # --- Memory ---------------------------------------------------------------

    @mcp.tool(annotations=RESEARCH)
    async def what_changed(
        company: str, domain: str | None = None, ctx: Context | None = None
    ) -> schemas.Changes:
        """What changed at a company since Scout last researched it.

        Researches it again and compares with the last snapshot from an earlier
        day: open roles rising or falling, teams that started or stopped hiring,
        technologies appearing in job posts, new Hacker News stories, GitHub going
        quiet, headcount changes.

        Args:
            company: Company name.
            domain: The company's website. Use the same one as before.
        """
        return changes_of(await dossier_for(company, domain, ctx))

    @mcp.tool(annotations=LOCAL_WRITE)
    def watch_company(company: str, domain: str | None = None) -> schemas.WatchResult:
        """Add a company to the watchlist that check_watchlist reviews.

        Args:
            company: Company name.
            domain: The company's website. Strongly recommended, so each check
                looks at the same company.
        """
        h = history()
        if len(h.watchlist()) >= MAX_WATCHLIST:
            raise ToolError(f"The watchlist is full ({MAX_WATCHLIST}); unwatch a company first.")
        added = h.watch(company, domain)
        note = ("Added." if added else "Already on the watchlist.") + (
            "" if domain else " Without a domain, checks rely on name matching.")
        return schemas.WatchResult(company=company, domain=domain, watching=True, note=note)

    @mcp.tool(annotations=LOCAL_WRITE)
    def unwatch_company(company: str, domain: str | None = None) -> schemas.WatchResult:
        """Remove a company from the watchlist."""
        removed = history().unwatch(company, domain)
        return schemas.WatchResult(company=company, domain=domain, watching=False,
                                   note="Removed." if removed else "It wasn't on the watchlist.")

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    def list_watchlist() -> schemas.Watchlist:
        """The companies on the watchlist."""
        return schemas.Watchlist(
            companies=[schemas.WatchedCompany(**c) for c in history().watchlist()]
        )

    @mcp.tool(annotations=RESEARCH)
    async def check_watchlist(ctx: Context | None = None) -> schemas.WatchlistCheck:
        """Research every watched company and report what changed at each.

        Takes 10-30 seconds per company; companies are checked one at a time to
        stay within GitHub's search limit.
        """
        watched = history().watchlist()
        results = []
        for i, c in enumerate(watched):
            if ctx is not None:
                await ctx.report_progress(i, len(watched), f"Checking {c['company']}")
            results.append(changes_of(await dossier_for(c["company"], c["domain"], None)))
        return schemas.WatchlistCheck(checked=len(results), results=results)

    # --- Web ------------------------------------------------------------------

    @mcp.tool(annotations=READ_ONLY_WEB)
    async def read_page(url: str, max_chars: int = 20_000) -> schemas.Page:
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
        return schemas.Page(**page.to_dict())

    @mcp.tool(annotations=READ_ONLY_WEB)
    async def github_research(
        company: str, domain: str | None = None, org: str | None = None
    ) -> schemas.GitHubResult:
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
        return schemas.GitHubResult(
            found=profile is not None, company=company,
            profile=profile.to_dict() if profile else None,
        )

    # --- Notes ----------------------------------------------------------------

    @mcp.tool(annotations=LOCAL_WRITE)
    def save_note(
        title: str, content: str, url: str | None = None, tags: list[str] | None = None
    ) -> schemas.Note:
        """Save a research finding to the user's local notebook.

        Args:
            title: Short, specific title.
            content: The finding, in markdown. Self-contained: it will be read later
                without this conversation.
            url: Source URL, if the note came from a page.
            tags: A few lowercase topic tags, e.g. ["stripe", "payments"].
        """
        return schemas.Note(**notebook().save(title, content, url=url, tags=tags).to_dict())

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    def search_notes(query: str, limit: int = 10) -> schemas.NoteSearch:
        """Search saved notes by keyword (best matches first, with highlighted snippets).

        Args:
            query: Words to look for in note titles, content and tags.
            limit: Maximum notes to return, 1-50.
        """
        hits = notebook().search(query, max(1, min(limit, 50)))
        return schemas.NoteSearch(results=[
            schemas.NoteHit(id=n.id, title=n.title, url=n.url, tags=n.tags, snippet=snip)
            for n, snip in hits
        ])

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    def list_notes(limit: int = 20, tag: str | None = None) -> schemas.NoteList:
        """Most recent saved notes, optionally only those with a tag.

        Args:
            limit: Maximum notes to return, 1-100.
            tag: Only notes carrying this tag.
        """
        notes = notebook().recent(max(1, min(limit, 100)), tag=tag)
        return schemas.NoteList(notes=[
            schemas.NoteSummary(id=n.id, title=n.title, url=n.url, tags=n.tags,
                                created_at=n.created_at)
            for n in notes
        ])

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    def get_note(note_id: int) -> schemas.Note:
        """Full content of one saved note."""
        note = notebook().get(note_id)
        if note is None:
            raise ToolError(f"No note with id {note_id}")
        return schemas.Note(**note.to_dict())

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False))
    def delete_note(note_id: int) -> schemas.Deleted:
        """Permanently delete a saved note."""
        if not notebook().delete(note_id):
            raise ToolError(f"No note with id {note_id}")
        return schemas.Deleted(deleted=note_id)

    @mcp.tool(annotations=LOCAL_WRITE)
    def export_notes(folder: str | None = None) -> schemas.Export:
        """Export every saved note as a Markdown file (for Obsidian or any notes app).

        Files are named scout-<id>-<title>.md with the note's tags and source in
        front matter; exporting again updates them. Nothing else in the folder is
        changed.

        Args:
            folder: An existing folder to write into, e.g. an Obsidian vault.
                Defaults to "markdown" inside Scout's notes folder.
        """
        if folder:
            target = Path(folder).expanduser()
            if not target.is_dir():
                raise ToolError(f"{folder} is not an existing folder.")
        else:
            target = config.data_dir / "markdown"
        files = notebook().export_markdown(target)
        return schemas.Export(folder=str(target), written=len(files),
                              files=[f.name for f in files])

    # --- Notes as resources (attachable in clients like Claude Desktop) -------

    @mcp.resource("scout://notes", name="Scout notebook", mime_type="text/markdown")
    def notes_index() -> str:
        """Every saved note, newest first, with its resource address."""
        notes = notebook().recent(200)
        lines = ["# Scout notebook", ""]
        lines += [f"- [{n.title}](scout://notes/{n.id}) · {', '.join(n.tags) or 'untagged'}"
                  f" · {n.created_at[:10]}" for n in notes]
        return "\n".join(lines) + "\n"

    @mcp.resource("scout://notes/{note_id}", name="Scout note", mime_type="text/markdown")
    def note_resource(note_id: str) -> str:
        """One saved note as Markdown."""
        note = notebook().get(int(note_id)) if note_id.isdigit() else None
        if note is None:
            raise ValueError(f"No note with id {note_id}")
        source = f"\n\nSource: {note.url}" if note.url else ""
        return f"# {note.title}\n\n{note.content}{source}\n"

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

    @mcp.prompt(title="Check my watchlist")
    def watchlist_review() -> str:
        """What changed at the companies I'm watching."""
        return """Check the companies on my watchlist.

1. Call check_watchlist.
2. Lead with the companies where something important changed: hiring
   falling or stopping, a team starting to hire, layoffs or funding in the
   news. For those, use your web search to find out why.
3. List the companies where nothing notable changed in one line each.
4. save_note a short summary tagged "watchlist"."""

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
