"""Runtime configuration, read from the environment.

Nothing here has a usable production default. ``SECRET_KEY`` in particular is
validated at startup: a platform holding animal-health records and farmer
contact details must not boot with a shipped signing key, so the app refuses to
start in production without one.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Long enough to satisfy the HMAC-SHA256 minimum key length (RFC 7518 s3.2)
#: so that development does not run on a configuration production would reject.
INSECURE_DEV_KEY = "dev-only-insecure-key-change-me-before-any-real-deployment"

#: Minimum signing-key length for HS256.
MIN_SECRET_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="VANRAKSHA_", extra="ignore"
    )

    environment: str = "development"
    debug: bool = False

    # SQLite keeps `docker compose up` and the test suite frictionless.
    # PostgreSQL with PostGIS is the deployment target; see docs/10-deployment.
    database_url: str = "sqlite:///./vanraksha.db"

    secret_key: str = INSECURE_DEV_KEY
    access_token_minutes: int = 60 * 12
    refresh_token_days: int = 30

    # Both spellings of the loopback host. A browser treats "localhost" and
    # "127.0.0.1" as different origins, so a dev default carrying only one of
    # them fails depending on which URL the developer happens to type.
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # Surveillance sweep parameters. Exposed so a district can tune detection to
    # its own reporting density without a redeploy.
    # Tuned in ml/evaluate_detector.py; see ClusterConfig for the trade-off and
    # why these must be re-tuned for a district with different reporting density.
    cluster_radius_km: float = 5.0
    cluster_window_hours: float = 120.0
    cluster_min_reports: int = 4
    anomaly_baseline_weeks: int = 10

    #: Optional. When unset, the assistant answers from deterministic templates.
    llm_api_key: str | None = None
    llm_model: str = "claude-sonnet-5"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalise_postgres_dsn(cls, value):
        """Pin PostgreSQL DSNs to psycopg 3.

        Managed providers hand out a driverless URL -- ``postgres://`` from
        Heroku-lineage services, ``postgresql://`` from most others. Neither
        names a driver, and SQLAlchemy resolves a bare ``postgresql`` to
        psycopg2, which this project does not install: it depends on psycopg 3.
        The result is a deployment that crashes on first connection with
        ``ModuleNotFoundError: psycopg2`` while the DSN looks perfectly correct,
        and ``postgres://`` is rejected by SQLAlchemy outright.

        Rewriting here rather than at the call site means every consumer of the
        setting -- the app, the CLI, Alembic, the tests -- gets the same URL,
        and an operator can paste whatever their provider gave them.
        """
        if not isinstance(value, str):
            return value
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod", "staging")

    def validate_for_runtime(self) -> None:
        """Fail loudly at startup rather than quietly running insecurely."""
        if len(self.secret_key.encode("utf-8")) < MIN_SECRET_BYTES:
            raise RuntimeError(
                f"VANRAKSHA_SECRET_KEY must be at least {MIN_SECRET_BYTES} bytes for HS256 "
                "(RFC 7518 section 3.2). Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if self.is_production and self.secret_key == INSECURE_DEV_KEY:
            raise RuntimeError(
                "VANRAKSHA_SECRET_KEY must be set to a unique value outside development. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if self.is_production and self.database_url.startswith("sqlite"):
            raise RuntimeError(
                "SQLite is a development convenience only. Set VANRAKSHA_DATABASE_URL to a "
                "PostgreSQL DSN before running outside development."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
