import logging

import httpx
from bs4 import BeautifulSoup
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.agents.github_research import ToolCaller, research_github
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=settings.openai_api_key)


async def fetch_company_website(url: str) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "lxml")
                text = soup.get_text(separator=" ", strip=True)
                return text[:3000]
    except Exception:
        pass
    return ""


async def research_company(
    company_name: str, domain: str | None = None, github: ToolCaller | None = None
) -> dict:
    website_text = ""
    if domain:
        website_text = await fetch_company_website(f"https://{domain}")

    github_profile = None
    if github is not None:
        try:
            github_profile = await research_github(company_name, github, domain=domain)
        except Exception as e:
            logger.warning("GitHub research failed for %s: %s", company_name, e)

    prompt = f"""Research this company and provide a structured analysis.

Company: {company_name}
Website content: {website_text[:2000] if website_text else "Not available"}
GitHub signals: {github_profile.to_prompt() if github_profile else "Not available"}

Provide a JSON-like response with these fields:
- mission: Company's mission statement or main purpose (1-2 sentences)
- goal: What they are working on ex(services, fintech, healthcare)
- tech_stack: Main technologies they use (comma-separated list)
- size: Company size estimate (e.g., "startup 1-10", "small 10-50", "medium 50-200", "large 200+")
- funding_stage: If known (e.g., "seed", "series_a", "series_b", "public", "unknown")
- summary: Brief company summary (2-3 sentences)

Be concise and factual. If you're unsure about something, say "unknown".
When GitHub signals are available, base tech_stack on them rather than on
general knowledge. If the match confidence is "low", the org may belong to a
different company with a similar name: only use it if the repos fit the company."""

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return {
        "raw_response": response.content,
        "company_name": company_name,
        "github": github_profile.to_dict() if github_profile else None,
    }
