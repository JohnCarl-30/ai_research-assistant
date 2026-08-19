"""OpenAI embedding generation."""

from openai import AsyncOpenAI

from app.config import get_settings

# The embeddings endpoint accepts many inputs per call; batching keeps indexing
# a full scan to a handful of round trips.
BATCH_SIZE = 128

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=get_settings().openai_api_key)
    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts, preserving input order."""
    if not texts:
        return []

    settings = get_settings()
    client = get_client()
    vectors: list[list[float]] = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=settings.embedding_dimensions,
        )
        # The API may return items out of order; `index` is the source of truth.
        for item in sorted(response.data, key=lambda d: d.index):
            vectors.append(list(item.embedding))

    return vectors


async def embed_query(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]
