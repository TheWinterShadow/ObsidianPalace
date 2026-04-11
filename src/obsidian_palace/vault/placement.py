"""AI-assisted file placement within the Obsidian vault.

Uses Claude to analyze the vault structure and incoming content
to determine the optimal location for new files.
"""

import logging

import httpx

from obsidian_palace.config import get_settings
from obsidian_palace.vault.operations import list_folders

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
PLACEMENT_MODEL = "claude-sonnet-4-20250514"


async def determine_placement(content: str, title: str | None = None) -> str:
    """Use AI to determine where a new note should be placed in the vault.

    Sends the vault's folder structure and the note's content to Claude,
    which returns a recommended path.

    Args:
        content: The markdown content of the note.
        title: Optional title for additional context.

    Returns:
        A relative path within the vault (e.g., "Projects/ObsidianPalace/design-notes.md").
    """
    settings = get_settings()

    if not settings.anthropic_api_key:
        # No API key — fall back to Inbox
        fallback = f"Inbox/{title or 'untitled'}.md"
        logger.warning("No Anthropic API key configured, using fallback: %s", fallback)
        return fallback

    folders = await list_folders()
    folder_tree = "\n".join(f"- {f}/" for f in folders)

    prompt = (
        "You are a file organization assistant for an Obsidian vault.\n\n"
        f"The vault has these top-level folders:\n{folder_tree}\n\n"
        f"A new note needs to be placed in the vault.\n"
        f"Title: {title or '(untitled)'}\n"
        f"Content preview (first 500 chars):\n{content[:500]}\n\n"
        "Respond with ONLY the relative file path where this note should go. "
        "Use existing folders when appropriate. Include the .md extension. "
        "Example: Projects/MyProject/meeting-notes.md"
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": PLACEMENT_MODEL,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15.0,
        )

    if resp.status_code != 200:
        fallback = f"Inbox/{title or 'untitled'}.md"
        logger.error("AI placement failed (%s), using fallback: %s", resp.status_code, fallback)
        return fallback

    result = resp.json()
    path = result["content"][0]["text"].strip()

    # Ensure it ends with .md
    if not path.endswith(".md"):
        path = f"{path}.md"

    logger.info("AI placement determined: %s", path)
    return path
