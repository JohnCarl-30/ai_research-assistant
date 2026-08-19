"""Prompt version registry for A/B testing and evaluation."""

from langchain_core.prompts import ChatPromptTemplate

from app.prompts.cover_letter import COVER_LETTER_PROMPT_V1, COVER_LETTER_PROMPT_V2
from app.prompts.research import RESEARCH_PROMPT_V1, RESEARCH_PROMPT_V2
from app.prompts.matching import MATCHING_PROMPT_V1, MATCHING_PROMPT_V2


# Version registry
PROMPT_VERSIONS: dict[str, dict[str, ChatPromptTemplate]] = {
    "cover_letter": {
        "v1": COVER_LETTER_PROMPT_V1,
        "v2": COVER_LETTER_PROMPT_V2,
    },
    "research": {
        "v1": RESEARCH_PROMPT_V1,
        "v2": RESEARCH_PROMPT_V2,
    },
    "matching": {
        "v1": MATCHING_PROMPT_V1,
        "v2": MATCHING_PROMPT_V2,
    },
}

# Default versions
DEFAULT_VERSIONS = {
    "cover_letter": "v2",
    "research": "v2",
    "matching": "v2",
}


def get_prompt(agent_type: str, version: str | None = None) -> ChatPromptTemplate:
    """Get a prompt by agent type and version."""
    if agent_type not in PROMPT_VERSIONS:
        raise ValueError(f"Unknown agent type: {agent_type}")

    versions = PROMPT_VERSIONS[agent_type]
    version = version or DEFAULT_VERSIONS.get(agent_type, "v1")

    if version not in versions:
        raise ValueError(f"Unknown version '{version}' for {agent_type}. Available: {list(versions.keys())}")

    return versions[version]


def list_versions() -> dict[str, list[str]]:
    """List all available prompt versions."""
    return {agent_type: list(versions.keys()) for agent_type, versions in PROMPT_VERSIONS.items()}


def get_latest_version(agent_type: str) -> str:
    """Get the latest version for an agent type."""
    if agent_type not in PROMPT_VERSIONS:
        raise ValueError(f"Unknown agent type: {agent_type}")
    versions = list(PROMPT_VERSIONS[agent_type].keys())
    return versions[-1]
