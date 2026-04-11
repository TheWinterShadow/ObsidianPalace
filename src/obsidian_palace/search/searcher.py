"""MemPalace search wrapper.

Provides a simplified interface to MemPalace's semantic search
capabilities, configured against the Obsidian vault's ChromaDB
persistence directory.
"""

import logging
from dataclasses import dataclass

from obsidian_palace.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result from MemPalace."""

    content: str
    source_path: str
    score: float
    metadata: dict


async def search(query: str, limit: int = 10) -> list[SearchResult]:
    """Search the vault index using MemPalace semantic search.

    Args:
        query: Natural language search query.
        limit: Maximum number of results.

    Returns:
        Ranked list of search results.
    """
    settings = get_settings()
    logger.info("Searching vault: query=%r, limit=%d, db=%s", query, limit, settings.chromadb_path)

    # TODO: Phase 3 — integrate with mempalace.searcher.search_memories
    # from mempalace.searcher import search_memories
    # results = search_memories(query, limit=limit, persist_directory=str(settings.chromadb_path))

    return []
