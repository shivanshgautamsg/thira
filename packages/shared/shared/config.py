"""THIRA platform configuration.

Central configuration loaded from environment variables and .env files.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ThiraConfig(BaseSettings):
    """Platform-wide configuration.

    Values are loaded from environment variables and .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── LLM ──────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # ── Database ─────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://thira:thira_dev@localhost:5432/thira"
    database_url_sync: str = "postgresql://thira:thira_dev@localhost:5432/thira"

    # ── Redis ────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── JARVIS ───────────────────────────────────────────────
    jarvis_host: str = "0.0.0.0"
    jarvis_port: int = 8000

    # ── Logging ──────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    # ── Google Workspace (Gmail & Calendar) ──────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_credentials_file: str = ""
    calendar_id: str = "primary"

    # Legacy alias support
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    # ── GitHub (Phase 2+) ────────────────────────────────────
    github_token: str = ""


def load_config() -> ThiraConfig:
    """Load and return the THIRA configuration."""
    return ThiraConfig()
