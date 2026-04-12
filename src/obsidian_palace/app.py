"""FastAPI application — serves MCP over SSE + Streamable HTTP and health endpoints.

The MCP server (with OAuth) runs as a Starlette sub-application mounted
under the root, serving both SSE (``/sse``) and Streamable HTTP (``/mcp``)
transports. Health and docs endpoints are served by FastAPI directly.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from obsidian_palace.__about__ import __version__
from obsidian_palace.config import get_settings
from obsidian_palace.mcp.transport import create_mcp_app, get_streamable_session_manager

logger = logging.getLogger(__name__)


async def _wait_for_vault_files(vault_path: Path, timeout: float = 120.0) -> int:
    """Wait for markdown files to appear in the vault.

    On fresh container starts, ``ob sync`` populates the vault concurrently
    with the MCP server. This function polls the vault directory for ``.md``
    files so the initial index runs after sync has written content, rather
    than indexing an empty directory.

    Args:
        vault_path: Absolute path to the vault root.
        timeout: Maximum seconds to wait before proceeding anyway.

    Returns:
        Number of ``.md`` files found when the wait ended.
    """
    interval = 3.0
    elapsed = 0.0
    count = 0

    while elapsed < timeout:
        count = sum(
            1
            for _ in vault_path.rglob("*.md")
            if not any(part.startswith(".") for part in _.relative_to(vault_path).parts)
        )
        if count > 0:
            logger.info("Vault has %d .md files — proceeding with indexing", count)
            return count
        await asyncio.sleep(interval)
        elapsed += interval

    logger.warning("Vault still empty after %.0fs — proceeding with indexing anyway", timeout)
    return count


async def _run_indexing() -> None:
    """Background task: wait for vault content, index, and start the file watcher.

    Waits for ``ob sync`` to populate the vault before running the initial
    full-vault index. The file watcher then handles incremental changes.
    Search returns empty results until the initial index completes, which
    is acceptable since the server starts immediately.
    """
    try:
        from obsidian_palace.search.indexer import index_vault
        from obsidian_palace.search.watcher import watch_vault

        settings = get_settings()
        await _wait_for_vault_files(settings.vault_path.resolve())

        files, drawers = await index_vault()
        logger.info(
            "Background vault indexing complete: %d files, %d drawers",
            files,
            drawers,
        )

        # Start the file watcher for incremental re-indexing.
        # This runs forever, so we just await it (it will be cancelled
        # when the indexing_task is cancelled during shutdown).
        await watch_vault()
    except ImportError:
        logger.warning(
            "MemPalace not available (requires Python 3.12 + chromadb) "
            "— search and indexing disabled"
        )
    except asyncio.CancelledError:
        logger.info("Vault indexing/watcher cancelled (shutdown)")
    except Exception:
        logger.exception("Background vault indexing failed — search disabled")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle.

    Vault indexing runs as a background task so the server starts
    accepting requests immediately. Search may be empty until the
    initial index completes.
    """
    settings = get_settings()
    logger.info(
        "ObsidianPalace v%s starting — vault=%s, chromadb=%s",
        __version__,
        settings.vault_path,
        settings.chromadb_path,
    )

    # Launch indexing as a background task — do NOT await it here.
    indexing_task: asyncio.Task | None = None

    if settings.mempalace_enabled:
        indexing_task = asyncio.create_task(_run_indexing(), name="vault-indexing")
        logger.info("Vault indexing started in background")
    else:
        logger.info("MemPalace disabled via configuration")

    # Start the Streamable HTTP session manager's task group.
    # Without this, /mcp requests fail with "Task group is not initialized".
    session_manager = get_streamable_session_manager()
    sm_ctx = None
    if session_manager is not None:
        sm_ctx = session_manager.run()
        await sm_ctx.__aenter__()
        logger.info("Streamable HTTP session manager started")

    yield

    # Shutdown: stop the session manager.
    if sm_ctx is not None:
        await sm_ctx.__aexit__(None, None, None)
        logger.info("Streamable HTTP session manager stopped")

    # Shutdown: cancel the background indexing/watcher task.
    if indexing_task is not None:
        indexing_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await indexing_task
        logger.info("Vault indexing/watcher stopped")

    logger.info("ObsidianPalace shutting down")


app = FastAPI(
    title="ObsidianPalace",
    version=__version__,
    description=(
        "MCP server bridging Obsidian vaults with AI via semantic search "
        "and bidirectional sync. Exposes vault tools over SSE and Streamable "
        "HTTP transports for Claude Desktop, OpenCode, and other MCP clients."
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


# Mount the MCP Starlette app.
# This handles: /sse, /messages/ (SSE transport), /mcp (Streamable HTTP),
# /.well-known/oauth-*, /authorize, /token, /register, /revoke, /oauth2/callback
mcp_app = create_mcp_app()
app.mount("/", mcp_app)
