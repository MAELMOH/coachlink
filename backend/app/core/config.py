"""Application settings, entirely driven by environment variables.

No secret ever has a real value here — defaults are dev-only placeholders and the
canonical list of variables lives in ``backend/.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="COACHLINK_",
        extra="ignore",
        case_sensitive=False,
    )

    # --- runtime ----------------------------------------------------------
    environment: Literal["dev", "test", "staging", "prod"] = "dev"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    project_name: str = "CoachLink API"

    #: OpenAPI is exposed in dev/test so `front` can generate the Dart models
    #: (ARCHITECTURE.md §8). Never exposed in prod.
    @property
    def expose_openapi(self) -> bool:
        return self.environment in ("dev", "test")

    # --- database ---------------------------------------------------------
    #: Connects as the *application* role: NOSUPERUSER, NOBYPASSRLS.
    #: Row Level Security is a real barrier only under such a role.
    database_url: str = (
        "postgresql+asyncpg://coachlink_app:coachlink_app_dev_only@localhost:5432/coachlink"
    )
    #: Owner/migration role, used by Alembic only.
    database_migration_url: str = (
        "postgresql+asyncpg://coachlink_owner:coachlink_owner_dev_only@localhost:5432/coachlink"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_echo: bool = False

    # --- redis ------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- auth -------------------------------------------------------------
    jwt_secret: SecretStr = SecretStr("dev-only-not-a-real-secret-change-me")
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    #: Argon2id parameters (OWASP-ish baseline; tuned down in tests for speed).
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 65536
    argon2_parallelism: int = 4

    # --- crypto (RGPD envelope encryption, ARCHITECTURE.md §5.1) ----------
    #: Base64 32-byte KEK. In staging/prod it comes from Scaleway Secret Manager,
    #: never from the repo. The dev default below is a well-known throwaway value.
    kek_b64: SecretStr = SecretStr("ZGV2LW9ubHkta2V5LTMyLWJ5dGVzLXBsYWNlaG9sZGVyISE=")
    kek_version: int = 1

    # --- object storage (S3-compatible: Scaleway Paris / MinIO in dev) ----
    s3_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "fr-par"
    s3_bucket_media: str = "coachlink-media"
    s3_bucket_exports: str = "coachlink-exports"
    # Matches the MinIO credentials in the repo-root docker-compose (dev only).
    s3_access_key: SecretStr = SecretStr("coachlink_dev")
    s3_secret_key: SecretStr = SecretStr("coachlink_dev_only")
    s3_presign_ttl_seconds: int = 300  # 5 min (§5.1)
    s3_export_presign_ttl_seconds: int = 86400  # 24 h (§5.3)

    # --- media limits (§6) ------------------------------------------------
    max_image_bytes: int = 5 * 1024 * 1024
    max_video_bytes: int = 100 * 1024 * 1024
    max_video_seconds: int = 60

    # --- business rules ---------------------------------------------------
    client_trial_days: int = 10
    invitation_ttl_hours: int = 168  # 7 days
    account_deletion_grace_days: int = 7
    inactive_account_months: int = 24
    minimum_age_years: int = 16
    default_timezone: str = "Europe/Paris"

    # --- rate limiting (§8) -----------------------------------------------
    rate_limit_per_minute: int = 100
    login_rate_limit_per_minute: int = 5
    rate_limit_enabled: bool = True

    # --- observability ----------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True
    sentry_dsn: str | None = None

    #: ``NoDecode`` is load-bearing, not decoration. Without it pydantic-settings
    #: JSON-decodes any complex-typed value *before* the validators run, so the
    #: comma-separated form documented in ``.env.example`` — and in particular the
    #: empty ``COACHLINK_CORS_ORIGINS=`` line, which is the correct value in prod —
    #: raises ``SettingsError`` and the app refuses to boot. Copying `.env.example`
    #: to `.env` must always produce a working app; that is what it is for.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment in ("staging", "prod")


@lru_cache
def get_settings() -> Settings:
    """Cached settings. Tests that flip env vars must call ``get_settings.cache_clear()``."""
    return Settings()
