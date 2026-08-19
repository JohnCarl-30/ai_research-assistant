"""Answer questions about indexed job postings, grounded in retrieved context.

Retrieval happens at chunk granularity but context is assembled per *posting*:
each chunk hit is expanded back to its whole job posting (see `build_contexts`).

This is the component the ragas harness scores. Faithfulness and context
precision/recall only mean something when the answer is constrained to the
retrieved contexts, so the prompt forbids outside knowledge and the assembled
context is returned alongside the answer for evaluation.
"""

from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.rag.retriever import RetrievedChunk, retrieve
from app.rag.vector_store import fetch_job_chunks

NO_ANSWER = "I don't have enough information in the indexed job postings to answer that."

SYSTEM_PROMPT = f"""You answer questions about job postings for a job seeker.

Rules:
- Use ONLY the numbered context passages provided. Do not use outside knowledge.
- If the contexts do not contain the answer, reply exactly: "{NO_ANSWER}"
- Cite the job title and company when referring to a specific posting.
- Each numbered passage is one distinct job posting. When listing roles, list
  each posting at most once.
- Be concise and concrete. Do not speculate about salary, seniority or
  requirements that are not stated in the contexts."""


@dataclass
class GroundedAnswer:
    question: str
    answer: str
    contexts: list[str] = field(default_factory=list)
    retrieved: list[RetrievedChunk] = field(default_factory=list)


def assemble_posting(chunks: list) -> str:
    """Rebuild one posting from its ordered chunks.

    Chunk 0 is the header-only overview and every later chunk repeats that same
    header, so the header is emitted once and stripped from the rest.
    """
    if not chunks:
        return ""

    header = chunks[0].content
    parts = [header]
    for chunk in chunks[1:]:
        body = chunk.content
        if body.startswith(header):
            body = body[len(header) :]
        body = body.strip()
        if body and body not in parts:
            parts.append(body)

    return "\n\n".join(parts)


async def build_contexts(session: AsyncSession, retrieved: list[RetrievedChunk]) -> list[str]:
    """One context passage per matched job, best-ranked job first.

    Two reasons this is not simply the list of retrieved chunk texts:

    1. Several chunks of the same posting can be retrieved together. Passing them
       through verbatim made the model enumerate one job as if it were several.
    2. A hit on the header-only overview chunk carries no body, so a question
       answerable from the posting got refused. Expanding each hit to its whole
       posting puts the answer back in context.
    """
    ordered_job_ids: list = list(dict.fromkeys(r.chunk.job_id for r in retrieved))
    grouped = await fetch_job_chunks(session, ordered_job_ids)

    contexts = []
    for job_id in ordered_job_ids:
        passage = assemble_posting(grouped.get(job_id, []))
        if passage:
            contexts.append(passage)
    return contexts


def build_context_block(contexts: list[str]) -> str:
    return "\n\n".join(f"[{i + 1}] {text}" for i, text in enumerate(contexts))


def get_answer_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.rag_answer_model,
        temperature=0,
        api_key=settings.openai_api_key,
    )


async def answer_job_question(
    session: AsyncSession,
    question: str,
    top_k: int | None = None,
    *,
    hybrid: bool = True,
) -> GroundedAnswer:
    """Retrieve relevant job chunks and answer strictly from them."""
    chunks = await retrieve(session, question, top_k=top_k, hybrid=hybrid)

    if not chunks:
        return GroundedAnswer(question=question, answer=NO_ANSWER, contexts=[], retrieved=[])

    contexts = await build_contexts(session, chunks)
    if not contexts:
        return GroundedAnswer(question=question, answer=NO_ANSWER, contexts=[], retrieved=chunks)

    response = await get_answer_llm().ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Context passages:\n\n{build_context_block(contexts)}\n\n"
                f"Question: {question}"
            ),
        ]
    )

    return GroundedAnswer(
        question=question,
        answer=str(response.content).strip(),
        contexts=contexts,
        retrieved=chunks,
    )
