"""Versioned prompts for Scout agents."""

from app.prompts.cover_letter import COVER_LETTER_PROMPT_V1, COVER_LETTER_PROMPT_V2
from app.prompts.research import RESEARCH_PROMPT_V1, RESEARCH_PROMPT_V2
from app.prompts.matching import MATCHING_PROMPT_V1, MATCHING_PROMPT_V2
from app.prompts.versions import get_prompt, list_versions

__all__ = [
    "COVER_LETTER_PROMPT_V1",
    "COVER_LETTER_PROMPT_V2",
    "RESEARCH_PROMPT_V1",
    "RESEARCH_PROMPT_V2",
    "MATCHING_PROMPT_V1",
    "MATCHING_PROMPT_V2",
    "get_prompt",
    "list_versions",
]
