"""Company research for the pipeline: Scout's dossier, summarised by an LLM.

The evidence comes from ``scout_mcp.company`` (extension/), the same keyless
dossier the Claude Desktop extension and Claude Code plugin build: Wikidata
facts, the website's tech stack, DNS, public job boards, GitHub and Hacker
News. The LLM only condenses that evidence into the fields the backend stores.
"""

import json
import logging

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from scout_mcp.company import research_company as build_dossier
from scout_mcp.sources.http import Fetcher

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=settings.openai_api_key)

# Dossier sections worth the prompt's tokens; the rest is bookkeeping.
EVIDENCE = ("facts", "website", "dns", "hiring", "github", "hacker_news", "gaps")


def _evidence(dossier: dict) -> str:
    evidence = {k: dossier.get(k) for k in EVIDENCE if dossier.get(k)}
    hiring = evidence.get("hiring")
    if hiring:
        # Sample roles and links add length, not signal.
        evidence["hiring"] = {k: v for k, v in hiring.items() if k != "sample_roles"}
    return json.dumps(evidence, ensure_ascii=False, default=str)[:8000]


async def research_company(
    company_name: str, domain: str | None = None, fetcher: Fetcher | None = None
) -> dict:
    try:
        dossier = (await build_dossier(
            company_name, domain=domain, fetcher=fetcher or Fetcher(),
            notebook=None, github_token=settings.github_token,
        )).to_dict()
    except Exception as e:
        # Research enriches a scan; it never fails one.
        logger.warning("Dossier failed for %s: %s", company_name, e)
        dossier = {"company": company_name, "domain": domain, "gaps": [f"Dossier failed: {e}"]}

    prompt = f"""Research this company and provide a structured analysis.

Company: {company_name}
Website: {dossier.get("domain") or "unknown"}
Evidence from public sources (JSON): {_evidence(dossier)}

Provide a JSON-like response with these fields:
- mission: Company's mission statement or main purpose (1-2 sentences)
- goal: What they are working on ex(services, fintech, healthcare)
- tech_stack: Main technologies they use (comma-separated list)
- size: Company size estimate (e.g., "startup 1-10", "small 10-50", "medium 50-200", "large 200+")
- funding_stage: If known (e.g., "seed", "series_a", "series_b", "public", "unknown")
- summary: Brief company summary (2-3 sentences)

Be concise and factual. If you're unsure about something, say "unknown".
Base tech_stack on the evidence (website fingerprint, technologies named in job
posts, GitHub) rather than on general knowledge, and size on the headcount and
open roles. If the GitHub confidence is "low", the org may belong to a different
company with a similar name: only use it if the repos fit the company."""

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return {
        "raw_response": response.content,
        "company_name": company_name,
        "domain": dossier.get("domain"),
        "github": dossier.get("github"),
        "dossier": dossier,
    }
