"""Split job postings into self-contained chunks for embedding.

Every chunk carries a short header (title, company, location, salary) so that a
chunk retrieved in isolation still says which job it belongs to. Without this a
requirements bullet like "5+ years of Go" is unattributable once retrieved.
"""

import re
from dataclasses import dataclass

MAX_CHARS = 1200
OVERLAP_CHARS = 150

# Blank line, or the start of a new bullet — the natural seams in a job posting.
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n|\n(?=\s*[-*•·]\s)")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class Chunk:
    text: str
    index: int
    section: str


def _clean(text: str) -> str:
    text = _WHITESPACE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _build_header(
    title: str,
    company: str | None,
    location: str | None,
    salary: str | None,
) -> str:
    head = title.strip() if title else "Untitled role"
    if company:
        head = f"{head} at {company.strip()}"
    parts = [head]
    if location:
        parts.append(f"Location: {location.strip()}")
    if salary:
        parts.append(f"Salary: {salary.strip()}")
    return "\n".join(parts)


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Split a single oversized paragraph, preferring sentence then word breaks."""
    pieces: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        if len(sentence) <= max_chars:
            if sentence.strip():
                pieces.append(sentence.strip())
            continue
        # Still too long (an unpunctuated wall of text) — break on words.
        words = sentence.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > max_chars and current:
                pieces.append(current)
                current = word
            else:
                current = candidate
        if current:
            pieces.append(current)
    return pieces


def _pack(paragraphs: list[str], max_chars: int, overlap_chars: int) -> list[str]:
    """Greedily pack paragraphs into windows, carrying a tail of overlap forward."""
    windows: list[str] = []
    current = ""

    for para in paragraphs:
        for piece in _hard_split(para, max_chars) if len(para) > max_chars else [para]:
            candidate = f"{current}\n\n{piece}".strip() if current else piece
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                windows.append(current)
                tail = current[-overlap_chars:] if overlap_chars else ""
                # Start the overlap at a word boundary so it reads cleanly.
                if tail and " " in tail:
                    tail = tail[tail.index(" ") + 1 :]
                current = f"{tail}\n\n{piece}".strip() if tail else piece
            else:
                current = piece

    if current:
        windows.append(current)
    return windows


def chunk_job(
    title: str,
    company: str | None = None,
    location: str | None = None,
    salary: str | None = None,
    description: str | None = None,
    requirements: str | None = None,
    *,
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[Chunk]:
    """Return ordered, header-prefixed chunks for one job posting.

    Chunk 0 is always an "overview" holding just the header, so a query naming a
    role or company matches even when the posting has no body text.
    """
    header = _build_header(title, company, location, salary)
    chunks: list[Chunk] = [Chunk(text=header, index=0, section="overview")]

    sections = (("description", description), ("requirements", requirements))
    for section, raw in sections:
        body = _clean(raw or "")
        if not body:
            continue

        paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(body) if p.strip()]
        # Leave room for the header we prepend to every chunk.
        budget = max(max_chars - len(header) - 2, 200)

        for window in _pack(paragraphs, budget, overlap_chars):
            chunks.append(
                Chunk(
                    text=f"{header}\n\n{window}",
                    index=len(chunks),
                    section=section,
                )
            )

    return chunks
