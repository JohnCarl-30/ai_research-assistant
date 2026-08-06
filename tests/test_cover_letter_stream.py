import json

import pytest
from httpx import AsyncClient

from app.agents.cover_letter import _build_skills_text
from app.agents.templates import COVER_LETTER_TEMPLATE


def test_template_invokes_with_correct_fields():
    prompt = COVER_LETTER_TEMPLATE.invoke(
        {
            "job_title": "Engineer",
            "company_name": "Acme",
            "job_description": "Build things",
            "requirements": "Python",
            "skills_text": "Python, FastAPI",
        }
    )
    messages = prompt.to_messages()
    assert len(messages) == 2
    assert messages[0].type == "system"
    assert "cover letter writer" in messages[0].content
    assert messages[1].type == "human"
    assert "Engineer" in messages[1].content
    assert "Acme" in messages[1].content


def test_build_skills_text_with_list():
    result = _build_skills_text(["Python", "Rust"])
    assert result == "Python, Rust"


def test_build_skills_text_with_none():
    result = _build_skills_text(None)
    assert "Python" in result
    assert "FastAPI" in result


def test_build_skills_text_with_empty_list():
    result = _build_skills_text([])
    assert "Python" in result


@pytest.mark.asyncio
async def test_cover_letter_stream_route_returns_sse(client: AsyncClient, monkeypatch):
    async def mock_stream(
        job_title,
        company_name,
        job_description=None,
        user_skills=None,
    ):
        event = {
            "type": "start",
            "job_title": job_title,
            "company_name": company_name,
        }
        yield f"data: {json.dumps(event)}\n\n"
        yield 'data: {"type": "token", "content": "Hello"}\n\n'
        yield 'data: {"type": "token", "content": " World"}\n\n'
        yield 'data: {"type": "end"}\n\n'

    monkeypatch.setattr(
        "app.agents.cover_letter_stream.generate_cover_letter_stream",
        mock_stream,
    )

    resp = await client.get(
        "/api/cover-letter",
        params={
            "job_title": "Engineer",
            "company_name": "Acme",
            "stream": "true",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"

    lines = [line for line in resp.text.split("\n") if line.startswith("data:")]
    assert len(lines) == 4

    events = [json.loads(line.removeprefix("data: ")) for line in lines]
    assert events[0]["type"] == "start"
    assert events[0]["job_title"] == "Engineer"
    assert events[1] == {"type": "token", "content": "Hello"}
    assert events[2] == {"type": "token", "content": " World"}
    assert events[3]["type"] == "end"


@pytest.mark.asyncio
async def test_cover_letter_non_stream_unchanged(client: AsyncClient, monkeypatch):
    async def mock_generate(
        job_title,
        company_name,
        job_description=None,
        user_skills=None,
    ):
        return {
            "cover_letter": "Dear Hiring Manager...",
            "job_title": job_title,
            "company_name": company_name,
        }

    monkeypatch.setattr("app.agents.cover_letter.generate_cover_letter", mock_generate)

    resp = await client.get(
        "/api/cover-letter",
        params={"job_title": "Engineer", "company_name": "Acme"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cover_letter"] == "Dear Hiring Manager..."
    assert data["job_title"] == "Engineer"
