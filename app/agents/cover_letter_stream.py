import json
from collections.abc import AsyncGenerator

from langchain_core.runnables.retry import RunnableRetry

from app.agents.cover_letter import _build_skills_text
from app.agents.templates import COVER_LETTER_TEMPLATE


def _format_sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def generate_cover_letter_stream(
    job_title: str,
    company_name: str,
    job_description: str | None = None,
    requirements: str | None = None,
    user_skills: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
        api_key=settings.openai_api_key,
    )
    retry_llm = RunnableRetry(bound=llm, max_attempts=3)

    prompt = COVER_LETTER_TEMPLATE.invoke(
        {
            "job_title": job_title,
            "company_name": company_name,
            "job_description": job_description or "Not provided",
            "requirements": requirements or "Not provided",
            "skills_text": _build_skills_text(user_skills),
        }
    )

    yield _format_sse({"type": "start", "job_title": job_title, "company_name": company_name})

    try:
        async for event in retry_llm.astream_events(prompt, version="v2"):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield _format_sse({"type": "token", "content": chunk.content})
    except Exception as e:
        yield _format_sse({"type": "error", "message": str(e)})
        return

    yield _format_sse({"type": "end"})
