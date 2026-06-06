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
        database_url: Async PostgreSQL DSN (``postgresql+asyncpg://``) used by
            the async document store and readiness probe.
        database_sync_url: Synchronous PostgreSQL DSN
            (``postgresql+psycopg://``) used by the synchronous ingestion
            section store. Defaults to ``database_url`` when unset, which is
            safe if the URL already carries a sync driver scheme.
        qdrant_url: Qdrant base URL used by the readiness probe.
        readiness_timeout_seconds: Per-dependency probe timeout budget.
        max_upload_bytes: Maximum accepted upload body size in bytes; an upload
            exceeding this is rejected with 413 before the body is fully read
            (DoS guard, NFR-008). Defaults to 50 MiB.
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
    database_sync_url: str | None = Field(default=None, alias="DATABASE_SYNC_URL")
    qdrant_url: str | None = Field(default=None, alias="QDRANT_URL")

    readiness_timeout_seconds: float = Field(
        default=2.0, alias="READINESS_TIMEOUT_SECONDS"
    )

    jwt_secret: str | None = Field(default=None, alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_audience: str = Field(default="rag-refinement-personal", alias="JWT_AUDIENCE")
    jwt_issuer: str | None = Field(default=None, alias="JWT_ISSUER")

    api_key_salt: str | None = Field(default=None, alias="API_KEY_SALT")

    rate_limit_default_per_minute: int = Field(
        default=60, alias="RATE_LIMIT_DEFAULT_PER_MINUTE"
    )
    rate_limit_sensitive_per_minute: int = Field(
        default=20, alias="RATE_LIMIT_SENSITIVE_PER_MINUTE"
    )

    max_upload_bytes: int = Field(
        default=50 * 1024 * 1024, alias="MAX_UPLOAD_BYTES"
    )


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance.

    Returns:
        The singleton Settings built from the current environment.
    """
    return Settings()
