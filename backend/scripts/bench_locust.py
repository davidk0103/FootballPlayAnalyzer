"""Run Locust headless and write summary JSON next to other benchmark artifacts."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.bench_common import capture_env, env_dict, run_id, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://localhost:8317")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--spawn-rate", type=int, default=5)
    parser.add_argument("--run-time", default="30s")
    parser.add_argument("--season", type=int, default=2024)
    args = parser.parse_args()

    database_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://playbookiq:playbookiq@localhost:5433/playbookiq"
    )
    with tempfile.TemporaryDirectory() as tmp:
        csv_prefix = str(Path(tmp) / "locust")
        cmd = [
            sys.executable,
            "-m",
            "locust",
            "-f",
            "loadtests/locustfile.py",
            "--host",
            args.host.rstrip("/"),
            "--headless",
            "-u",
            str(args.users),
            "-r",
            str(args.spawn_rate),
            "--run-time",
            args.run_time,
            "--csv",
            csv_prefix,
            "--only-summary",
        ]
        subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], check=True)
        stats_path = Path(f"{csv_prefix}_stats.csv")
        rows = stats_path.read_text().strip().splitlines()
        header = rows[0].split(",") if rows else []
        aggregated = rows[-1].split(",") if len(rows) > 1 else []
        data = dict(zip(header, aggregated, strict=False)) if header and aggregated else {}

    payload = {
        "run_id": run_id(),
        "kind": "locust",
        "host": args.host,
        "users": args.users,
        "spawn_rate": args.spawn_rate,
        "run_time": args.run_time,
        "season": args.season,
        "environment": env_dict(capture_env(database_url, [args.season])),
        "aggregated": data,
    }
    out = write_json("locust.json", payload)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
