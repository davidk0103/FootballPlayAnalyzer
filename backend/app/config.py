from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://playbookiq:playbookiq@localhost:5432/playbookiq"
    data_cache_dir: Path = Path("data/cache")
    nflverse_pbp_base_url: str = "https://github.com/nflverse/nflverse-data/releases/download/pbp"
    nflverse_players_url: str = (
        "https://github.com/nflverse/nflverse-data/releases/download/players/players.parquet"
    )
    cors_origins: list[str] = ["http://localhost:5317", "http://127.0.0.1:5317"]
    ingest_chunk_size: int = 5000
    min_sample_warning: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
