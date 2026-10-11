"""Run EXPLAIN ANALYZE on analytics-related queries and store the plans."""

from __future__ import annotations

import argparse
import os
from typing import Any

from sqlalchemy import create_engine, text

from scripts.bench_common import capture_env, env_dict, run_id, write_json

QUERIES: dict[str, str] = {
    "plays_by_season": """
        SELECT count(*) FROM plays WHERE season = :season
    """,
    "team_comparison_frame": """
        SELECT game_id, play_id, offense, defense, epa, success, down, yards_to_go
        FROM plays
        WHERE season = :season AND offense IN ('KC', 'PHI')
        LIMIT 50000
    """,
    "latest_dataset": """
        SELECT id, season, sha256, imported_at
        FROM datasets
        WHERE season = :season
        ORDER BY imported_at DESC
        LIMIT 1
    """,
    "queued_jobs": """
        SELECT status, count(*) FROM jobs
        WHERE status IN ('queued', 'retrying', 'running')
        GROUP BY status
    """,
}


def explain(database_url: str, season: int) -> dict[str, Any]:
    engine = create_engine(database_url)
    plans: dict[str, Any] = {}
    with engine.connect() as conn:
        for name, sql in QUERIES.items():
            plan = conn.execute(
                text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"),
                {"season": season},
            ).scalar_one()
            plans[name] = plan[0] if isinstance(plan, list) else plan
    return plans


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2024)
    args = parser.parse_args()
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://playbookiq:playbookiq@localhost:5433/playbookiq"
    )
    payload = {
        "run_id": run_id(),
        "kind": "explain_analyze",
        "season": args.season,
        "environment": env_dict(capture_env(database_url, [args.season])),
        "plans": explain(database_url, args.season),
    }
    out = write_json("explain.json", payload)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
