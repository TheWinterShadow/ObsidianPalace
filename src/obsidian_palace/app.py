"""FastAPI application — serves MCP over SSE and health endpoints."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from obsidian_palace.__about__ import __version__
from obsidian_palace.config import get_settings
from obsidian_palace.mcp.transport import create_mcp_routes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle.

    Mounts MCP transport, runs initial vault indexing, and starts
    the file watcher for incremental re-indexing.
    """
    settings = get_settings()
    logger.info(
        "ObsidianPalace v%s starting — vault=%s, chromadb=%s",
        __version__,
        settings.vault_path,
        settings.chromadb_path,
    )

    # Mount MCP SSE routes
    mcp_mount = create_mcp_routes()
    app.router.routes.append(mcp_mount)
    logger.info("MCP SSE transport mounted at /mcp/sse")

    # Start MemPalace indexing and file watcher
    watcher_task: asyncio.Task | None = None

    if settings.mempalace_enabled:
        try:
            from obsidian_palace.search.indexer import index_vault
            from obsidian_palace.search.watcher import watch_vault

            files, drawers = await index_vault()
            logger.info(
                "Initial vault indexing: %d files processed, %d drawers",
                files,
                drawers,
            )

            watcher_task = asyncio.create_task(watch_vault(), name="vault-watcher")
            logger.info("Vault file watcher started")
        except ImportError:
            logger.warning(
                "MemPalace not available (requires Python 3.12 + chromadb) "
                "— search and indexing disabled"
            )
        except Exception:
            logger.exception("Failed to start MemPalace indexing — search disabled")
    else:
        logger.info("MemPalace disabled via configuration")

    yield

    # Shutdown: cancel watcher task
    if watcher_task is not None:
        watcher_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher_task
        logger.info("Vault file watcher stopped")

    logger.info("ObsidianPalace shutting down")


app = FastAPI(
    title="ObsidianPalace",
    version=__version__,
    description=(
        "MCP server bridging Obsidian vaults with AI via semantic search "
        "and bidirectional sync. Exposes vault tools over SSE transport "
        "for Claude Desktop, Claude iOS, claude.ai, and other MCP clients."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint for GCE instance monitoring."""
    return {"status": "ok", "version": __version__}
