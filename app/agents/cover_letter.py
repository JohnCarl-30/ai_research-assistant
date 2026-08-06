from app.agents.templates import COVER_LETTER_TEMPLATE


def _build_skills_text(user_skills: list[str] | None) -> str:
    if user_skills:
        return ", ".join(user_skills)
    return "Python, JavaScript, FastAPI, React, AWS, LangChain, PostgreSQL"


async def generate_cover_letter(
    job_title: str,
    company_name: str,
    job_description: str | None = None,
    requirements: str | None = None,
    user_skills: list[str] | None = None,
) -> dict:
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
        api_key=settings.openai_api_key,
    )

    prompt = COVER_LETTER_TEMPLATE.invoke(
        {
            "job_title": job_title,
            "company_name": company_name,
            "job_description": job_description or "Not provided",
            "requirements": requirements or "Not provided",
            "skills_text": _build_skills_text(user_skills),
        }
    )

    response = await llm.ainvoke(prompt)

    return {
        "cover_letter": response.content,
        "job_title": job_title,
        "company_name": company_name,
    }
