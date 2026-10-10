"""Ingestion CLI.

Usage (from backend/):
    uv run python -m app.ingest --seasons 2023,2024 [--force] [--cache-dir DIR]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from app.db import get_sessionmaker
from app.ingest.service import IngestError, ingest_season


def parse_seasons(value: str) -> list[int]:
    seasons = [int(s) for s in value.split(",") if s.strip()]
    if not seasons or any(s < 1999 or s > 2100 for s in seasons):
        raise argparse.ArgumentTypeError("seasons must be comma-separated years >= 1999")
    return seasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ingest", description=__doc__)
    parser.add_argument("--seasons", type=parse_seasons, required=True)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="re-import even if checksum matches")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    exit_code = 0
    with get_sessionmaker()() as session:
        for season in args.seasons:
            try:
                summary = ingest_season(
                    session,
                    season,
                    cache_dir=args.cache_dir,
                    chunk_size=args.chunk_size,
                    force=args.force,
                )
            except IngestError as exc:
                logging.error("%s", exc)
                exit_code = 1
                continue
            print(json.dumps(summary.as_dict(), indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
