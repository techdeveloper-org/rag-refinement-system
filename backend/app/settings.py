"""Application settings sourced from the 12-factor environment.

All configuration is read from environment variables (or an optional local
``.env`` file in development) via pydantic-settings. No secret values are
defaulted here; provider keys resolve to ``None`` when unset so the process
starts in development without credentials, while readiness reporting still
reflects which dependencies are configured.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view over the runtime environment.

    Attributes:
        app_name: Human-readable service name surfaced in probes and logs.
        app_version: Service version string reported by the liveness probe.
        database_url: PostgreSQL DSN used by the readiness probe.
        qdrant_url: Qdrant base URL used by the readiness probe.
        readiness_timeout_seconds: Per-dependency probe timeout budget.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="rag-refinement-system")
    app_version: str = Field(default="0.1.0")

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    qdrant_url: str | None = Field(default=None, alias="QDRANT_URL")

    readiness_timeout_seconds: float = Field(
        default=2.0, alias="READINESS_TIMEOUT_SECONDS"
    )


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance.

    Returns:
        The singleton Settings built from the current environment.
    """
    return Settings()
