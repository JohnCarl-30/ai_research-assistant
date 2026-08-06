import re

from app.config import TECH_PHRASES, TECH_SINGLE_WORDS


def extract_tags(text: str | None) -> list[str]:
    if not text:
        return []

    text_lower = text.lower()
    tags: list[str] = []

    for phrase in TECH_PHRASES:
        if phrase in text_lower:
            tags.append(phrase)

    for word in TECH_SINGLE_WORDS:
        pattern = rf"\b{re.escape(word)}\b"
        if re.search(pattern, text_lower):
            tags.append(word)

    return list(dict.fromkeys(tags))


def extract_source_tags(raw_tags: list[str] | None) -> list[str]:
    if not raw_tags:
        return []
    return [tag.strip().lower() for tag in raw_tags if tag.strip()]
