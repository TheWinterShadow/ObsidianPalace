"""MemPalace search wrapper.

Provides a simplified interface to MemPalace's semantic search
capabilities, configured against the Obsidian vault's ChromaDB
persistence directory.

MemPalace is entirely synchronous — all calls are wrapped with
``asyncio.to_thread`` to avoid blocking the FastAPI event loop.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from obsidian_palace.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result from MemPalace."""

    content: str
    source_path: str
    score: float
    metadata: dict = field(default_factory=dict)


def _search_sync(
    query: str,
    palace_path: str,
    wing: str | None = None,
    n_results: int = 10,
) -> list[SearchResult]:
    """Synchronous search via MemPalace — runs in a thread.

    Uses ``mempalace.searcher.search_memories`` which returns
    structured data suitable for programmatic consumption.
    """
    from mempalace.searcher import search_memories

    response = search_memories(
        query=query,
        palace_path=palace_path,
        wing=wing,
        n_results=n_results,
    )

    if "error" in response:
        logger.warning("MemPalace search error: %s", response["error"])
        return []

    results: list[SearchResult] = []
    for item in response.get("results", []):
        results.append(
            SearchResult(
                content=item.get("text", ""),
                source_path=item.get("source_file", ""),
                score=item.get("similarity", 0.0),
                metadata={
                    "wing": item.get("wing", ""),
                    "room": item.get("room", ""),
                },
            )
        )

    return results


async def search(query: str, limit: int = 10) -> list[SearchResult]:
    """Search the vault index using MemPalace semantic search.

    Wraps the synchronous MemPalace ``search_memories`` call in
    ``asyncio.to_thread`` so it does not block the event loop.

    Args:
        query: Natural language search query.
        limit: Maximum number of results.

    Returns:
        Ranked list of search results.
    """
    settings = get_settings()

    if not settings.mempalace_enabled:
        logger.debug("MemPalace disabled — returning empty results")
        return []

    palace_path = str(settings.chromadb_path)
    wing = settings.mempalace_wing

    logger.info(
        "Searching vault: query=%r, limit=%d, palace=%s, wing=%s",
        query,
        limit,
        palace_path,
        wing,
    )

    return await asyncio.to_thread(
        _search_sync,
        query=query,
        palace_path=palace_path,
        wing=wing,
        n_results=limit,
    )
