from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me-0123456789"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+psycopg://playbookiq:playbookiq@localhost:5432/playbookiq"
    data_cache_dir: Path = Path("data/cache")
    nflverse_pbp_base_url: str = "https://github.com/nflverse/nflverse-data/releases/download/pbp"
    nflverse_players_url: str = (
        "https://github.com/nflverse/nflverse-data/releases/download/players/players.parquet"
    )
    cors_origins: list[str] = ["http://localhost:5317", "http://127.0.0.1:5317"]
    ingest_chunk_size: int = 5000
    min_sample_warning: int = 30

    # Redis: Celery broker (db 0 by default) and analytics cache (db 1 by default).
    broker_url: str = "redis://localhost:6379/0"
    cache_url: str = "redis://localhost:6379/1"
    # Unacked messages are redelivered after this long (Redis transport). Must exceed the
    # longest job runtime plus the longest retry countdown, or jobs get delivered twice.
    broker_visibility_timeout_seconds: int = 3600

    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    cache_socket_timeout_seconds: float = 0.25
    # After a Redis error, skip the cache for this long instead of paying the timeout per request.
    cache_retry_after_seconds: float = 15.0

    job_max_attempts: int = 4
    job_retry_base_seconds: float = 2.0
    job_retry_max_seconds: float = 60.0
    job_timeout_seconds: int = 900
    job_heartbeat_seconds: float = 5.0
    # RUNNING jobs without a heartbeat for this long are considered lost by the reaper.
    job_stale_after_seconds: float = 60.0
    # QUEUED/RETRYING jobs untouched this long past their due time are re-enqueued by the reaper.
    job_requeue_after_seconds: float = 120.0
    reaper_interval_seconds: float = 30.0
    # Auth: JWT in an httpOnly cookie. The default secret is refused outside development/test.
    jwt_secret: str = DEV_JWT_SECRET
    jwt_ttl_hours: float = 12.0
    session_cookie_name: str = "piq_session"
    cookie_secure: bool = False
    # Unsafe requests (POST/PUT/PATCH/DELETE) must send this header with value "1".
    csrf_header_name: str = "X-PlaybookIQ-CSRF"
    rate_limit_enabled: bool = True

    # Test-only: lets integration tests inject faults via Redis keys. Never enable in production.
    enable_fault_injection: bool = False

    def check_secrets(self) -> None:
        """Refuse to run in production with the development JWT secret or a short one."""
        if self.environment == "production" and (
            self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32
        ):
            raise RuntimeError("JWT_SECRET must be set to a random value of 32+ characters")


@lru_cache
def get_settings() -> Settings:
    return Settings()
