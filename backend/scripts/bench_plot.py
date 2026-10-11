"""Render PNG charts from the latest benchmark JSON in benchmarks/results/."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt

from scripts.bench_common import repo_root, results_dir


def latest_run() -> Path:
    runs = sorted(results_dir().iterdir(), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise SystemExit("no benchmark runs in benchmarks/results/")
    return runs[-1]


def plot_http(run_dir: Path, out_dir: Path) -> Path | None:
    path = run_dir / "http.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    names = []
    p50 = []
    p95 = []
    rps = []
    for name, block in data["endpoints"].items():
        names.append(name)
        lat = block["latency_seconds"]
        p50.append(lat["p50"] * 1000)
        p95.append(lat["p95"] * 1000)
        rps.append(block["rps"])

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].bar(names, p50, label="p50")
    axes[0].bar(names, p95, alpha=0.5, label="p95")
    axes[0].set_ylabel("ms")
    axes[0].set_title("HTTP latency")
    axes[0].legend()
    axes[1].bar(names, rps, color="#2563eb")
    axes[1].set_ylabel("req/s")
    axes[1].set_title("HTTP throughput")
    fig.tight_layout()
    out = out_dir / "http-latency-rps.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def plot_workers(run_dir: Path, out_dir: Path) -> Path | None:
    path = run_dir / "workers.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    xs = [row["worker_containers"] for row in data["runs"]]
    ys = [row["jobs_per_minute"] for row in data["runs"]]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, marker="o")
    ax.set_xlabel("worker containers")
    ax.set_ylabel("imports / minute")
    ax.set_title("Parallel import throughput")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = out_dir / "worker-scaling.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=None)
    args = parser.parse_args()
    run_dir = args.run or latest_run()
    charts = repo_root() / "docs" / "benchmarks" / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    written = [p for fn in (plot_http, plot_workers) if (p := fn(run_dir, charts))]
    for p in written:
        print(p)


if __name__ == "__main__":
    main()
