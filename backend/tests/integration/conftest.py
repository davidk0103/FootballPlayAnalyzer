import os
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
import redis
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.cache import get_cache
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.ingest.service import IngestSummary, ingest_season
from app.ingest.source import SourceFile, sha256_file
from tests.conftest import PBP_SAMPLE, PLAYERS_SAMPLE

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://playbookiq:playbookiq@localhost:5432/playbookiq_test",
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379").rstrip("/")
TEST_BROKER_URL = f"{TEST_REDIS_URL}/14"
TEST_CACHE_URL = f"{TEST_REDIS_URL}/15"
BACKEND_DIR = Path(__file__).resolve().parents[2]

# Set before anything imports app.worker.celery_app, which reads the broker URL at import.
os.environ["BROKER_URL"] = TEST_BROKER_URL
os.environ["CACHE_URL"] = TEST_CACHE_URL


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_cache.cache_clear()

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    eng = create_engine(TEST_DATABASE_URL)
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A session whose commits are savepoints inside a transaction rolled back after the test."""
    with engine.connect() as conn:
        trans = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            trans.rollback()


@pytest.fixture(scope="session")
def player_directory() -> pd.DataFrame:
    return pd.read_parquet(PLAYERS_SAMPLE).set_index("gsis_id")


def fixture_source(path: Path = PBP_SAMPLE) -> SourceFile:
    return SourceFile(
        url=f"file://{path.name}", path=path, sha256=sha256_file(path), version="test"
    )


def ingest_fixture(
    session: Session, directory: pd.DataFrame, path: Path = PBP_SAMPLE, **kwargs: object
) -> IngestSummary:
    return ingest_season(
        session,
        2023,
        source=fixture_source(path),
        player_directory=directory,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.fixture
def seeded_session(db_session: Session, player_directory: pd.DataFrame) -> Session:
    ingest_fixture(db_session, player_directory)
    return db_session


@pytest.fixture(autouse=True)
def clean_redis() -> Iterator[None]:
    """Fresh analytics cache (and fault config) for every integration test."""
    client = redis.Redis.from_url(TEST_CACHE_URL)
    client.flushdb()
    get_cache.cache_clear()
    yield
    client.flushdb()
