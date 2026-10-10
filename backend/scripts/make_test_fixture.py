"""Build the trimmed real-data fixtures under tests/fixtures/ from cached nflverse files.

Usage (from backend/, after `make profile` or an ingest has cached the files):
    uv run python -m scripts.make_test_fixture
"""

from pathlib import Path

import pandas as pd

from app.config import get_settings
from app.ingest.columns import PLAYER_COLUMNS, REQUIRED_COLUMNS

GAMES = ["2023_01_DET_KC", "2023_01_ARI_WAS"]
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main() -> None:
    cache = get_settings().data_cache_dir
    pbp = pd.read_parquet(cache / "play_by_play_2023.parquet", columns=REQUIRED_COLUMNS)
    sample = pbp[pbp["game_id"].isin(GAMES)].reset_index(drop=True)
    OUT.mkdir(parents=True, exist_ok=True)
    sample.to_parquet(OUT / "pbp_2023_sample.parquet", index=False)

    ids = set()
    for col in PLAYER_COLUMNS:
        ids |= set(sample[col].dropna())
    players = pd.read_parquet(
        cache / "players.parquet", columns=["gsis_id", "display_name", "position"]
    )
    players[players["gsis_id"].isin(ids)].to_parquet(OUT / "players_sample.parquet", index=False)
    print(f"{len(sample)} plays from {GAMES}; {len(ids)} players")


if __name__ == "__main__":
    main()
