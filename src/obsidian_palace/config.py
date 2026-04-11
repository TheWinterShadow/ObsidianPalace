"""Application configuration via environment variables and pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ObsidianPalace configuration.

    Loads from environment variables with the OBSIDIAN_PALACE_ prefix.
    In local dev, reads from a `.env` file. In production, values are
    injected via GCP Secret Manager.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OBSIDIAN_PALACE_",
        extra="ignore",
    )

    # --- Google OAuth 2.0 ---
    google_client_id: str = ""
    google_client_secret: str = ""
    allowed_email: str = ""

    # --- Vault ---
    vault_path: Path = Path("/data/vault")
    chromadb_path: Path = Path("/data/chromadb")

    # --- MemPalace / Search ---
    mempalace_wing: str = "obsidian"
    mempalace_collection_name: str = "mempalace_drawers"
    mempalace_enabled: bool = True

    # --- Obsidian Sync ---
    obsidian_sync_mode: str = "bidirectional"

    # --- AI Placement ---
    anthropic_api_key: str = ""

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Retrieve the singleton application settings instance.

    Returns:
        The cached configuration settings.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
