"""Profile nflverse play-by-play parquet files and record findings in docs/data.md.

Usage (from backend/):
    uv run python -m scripts.profile_pbp --seasons 2023,2024 --docs ../docs/data.md
"""

import argparse
import re
from pathlib import Path

import pandas as pd

from app.config import get_settings
from app.ingest.columns import PLAYER_COLUMNS, REQUIRED_COLUMNS
from app.ingest.source import SourceFile, download, fetch_pbp

START_MARKER = "<!-- PROFILE:START -->"
END_MARKER = "<!-- PROFILE:END -->"
RELOCATED = {"OAK": "LV", "SD": "LAC", "STL": "LA"}


def pct(part: int | float, whole: int | float) -> str:
    return "n/a" if whole == 0 else f"{100 * part / whole:.2f}%"


def flag(df: pd.DataFrame, col: str) -> "pd.Series[bool]":
    return df[col].fillna(0).astype(int).eq(1)


def profile_season(src: SourceFile, df: pd.DataFrame) -> list[str]:
    season = int(df["season"].iloc[0])
    dupes = int(df.duplicated(["game_id", "play_id"]).sum())
    lines: list[str] = [f"### {season}", ""]
    lines += [
        f"- File: `{src.url.rsplit('/', 1)[-1]}`, SHA-256 `{src.sha256}`",
        f"- Rows: {len(df):,}; columns: {df.shape[1]}; games: {df['game_id'].nunique()}",
        f"- Season types: {df.groupby('season_type')['game_id'].nunique().to_dict()} (games)",
        f"- Weeks: {int(df['week'].min())}-{int(df['week'].max())}",
        f"- Duplicate `(game_id, play_id)` keys: {dupes}",
        "",
    ]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    lines.append(f"- Required columns missing: {missing or 'none'}")

    pt = df["play_type"].value_counts(dropna=False)
    pt_str = ", ".join(f"`{k}` {v:,}" for k, v in pt.items())
    lines.append(f"- `play_type` values: {pt_str}")

    teams = sorted(set(df["home_team"].dropna()) | set(df["away_team"].dropna()))
    posteam = sorted(df["posteam"].dropna().unique())
    lines.append(f"- Team abbreviations ({len(teams)}): {', '.join(teams)}")
    old = [t for t in RELOCATED if t in teams]
    lines.append(
        f"- Legacy abbreviations present: {old or 'none'}; "
        f"`posteam` values match home/away set: {posteam == teams}"
    )

    scrim = df[df["play_type"].isin(["pass", "run"])]
    lines += ["", "Null rates (all rows / pass+run rows):", ""]
    lines.append("| Column | All rows | Pass+run |")
    lines.append("| --- | --- | --- |")
    for col in REQUIRED_COLUMNS:
        if col in df.columns:
            all_null = int(df[col].isna().sum())
            sc_null = int(scrim[col].isna().sum())
            lines.append(f"| `{col}` | {pct(all_null, len(df))} | {pct(sc_null, len(scrim))} |")
    lines.append("")

    lines += profile_edge_cases(df, scrim)
    lines.append("")
    return lines


def profile_edge_cases(df: pd.DataFrame, scrim: pd.DataFrame) -> list[str]:
    out: list[str] = ["Edge cases:", ""]
    no_play = df[df["play_type"] == "no_play"]
    np_pen = int(flag(no_play, "penalty").sum())
    out.append(
        f"- `no_play` rows: {len(no_play):,}; with `penalty == 1`: "
        f"{np_pen:,} ({pct(np_pen, len(no_play))}); "
        f"with `first_down_penalty == 1`: {int(flag(no_play, 'first_down_penalty').sum()):,}; "
        f"with non-null `epa`: {int(no_play['epa'].notna().sum()):,}"
    )
    accepted = scrim[flag(scrim, "penalty")]
    out.append(
        f"- Pass+run rows with `penalty == 1` (penalty on a play that stood): {len(accepted):,}"
    )

    third = df[df["down"] == 3]
    conv = third[flag(third, "third_down_converted")]
    conv_pen = conv[flag(conv, "first_down_penalty")]
    conv_noplay = conv[conv["play_type"] == "no_play"]
    failed = third[flag(third, "third_down_failed")]
    neither = third[~flag(third, "third_down_converted") & ~flag(third, "third_down_failed")]
    out.append(
        f"- Third-down rows: {len(third):,}; `third_down_converted == 1`: {len(conv):,}; "
        f"`third_down_failed == 1`: {len(failed):,}; neither: {len(neither):,} "
        f"(play types of 'neither': {neither['play_type'].value_counts(dropna=False).to_dict()})"
    )
    out.append(
        f"- Converted third downs that were first downs by penalty: {len(conv_pen):,} "
        f"(of which `no_play`: {len(conv_noplay):,}; "
        f"play types {conv_pen['play_type'].value_counts(dropna=False).to_dict()})"
    )
    s_third = scrim[scrim["down"] == 3]
    out.append(
        f"- Pass+run third downs: {len(s_third):,}; converted: "
        f"{int(flag(s_third, 'third_down_converted').sum()):,}; failed: "
        f"{int(flag(s_third, 'third_down_failed').sum()):,}"
    )

    for col in ["qb_kneel", "qb_spike", "two_point_attempt", "aborted_play", "play_deleted"]:
        out.append(
            f"- `{col} == 1`: {int(flag(df, col).sum()):,} rows "
            f"({int(flag(scrim, col).sum()):,} within pass+run)"
        )
    out.append(
        f"- Pass+run rows with null `down` (e.g. two-point tries): "
        f"{int(scrim['down'].isna().sum()):,}; with null `posteam`: "
        f"{int(scrim['posteam'].isna().sum()):,}"
    )
    with_epa = scrim[scrim["epa"].notna()]
    mismatch = int(
        (with_epa["success"].fillna(-1).astype(int) != with_epa["epa"].gt(0).astype(int)).sum()
    )
    out.append(f"- Pass+run rows where `success != (epa > 0)`: {mismatch:,}")
    sack_type = scrim[flag(scrim, "sack")]["play_type"].value_counts().to_dict()
    scr_type = scrim[flag(scrim, "qb_scramble")]["play_type"].value_counts().to_dict()
    out.append(f"- Sacks by `play_type`: {sack_type}; scrambles by `play_type`: {scr_type}")
    clean = scrim[
        ~flag(scrim, "two_point_attempt")
        & ~flag(scrim, "aborted_play")
        & ~flag(scrim, "play_deleted")
        & scrim["posteam"].notna()
    ]
    per_team = clean.groupby(["posteam", "season_type"]).size().unstack(fill_value=0)
    if "REG" in per_team:
        out.append(
            f"- Regular-season scrimmage plays per offense: mean {per_team['REG'].mean():.0f}, "
            f"min {per_team['REG'].min()}, max {per_team['REG'].max()}"
        )
    return out


def profile_players(path: Path, frames: list[pd.DataFrame]) -> list[str]:
    players = pd.read_parquet(path)
    ids = set(players["gsis_id"].dropna())
    lines = [
        "### Players release",
        "",
        f"- `players.parquet`: {len(players):,} rows; key column `gsis_id` "
        f"({players['gsis_id'].notna().sum():,} non-null, "
        f"{players['gsis_id'].dropna().duplicated().sum()} duplicates)",
        f"- Name/position columns available: "
        f"{[c for c in ('display_name', 'position', 'position_group') if c in players.columns]}",
    ]
    for df in frames:
        season = int(df["season"].iloc[0])
        used = set()
        for col in PLAYER_COLUMNS:
            used |= set(df[col].dropna())
        found = len(used & ids)
        lines.append(
            f"- {season}: {len(used):,} distinct passer/rusher/receiver IDs, "
            f"{found:,} found in players release ({pct(found, len(used))})"
        )
    lines.append("")
    return lines


def write_section(doc: Path, body: str) -> None:
    text = doc.read_text()
    block = f"{START_MARKER}\n{body.rstrip()}\n{END_MARKER}"
    if START_MARKER in text and END_MARKER in text:
        pattern = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.S)
        text = pattern.sub(lambda _: block, text)
    else:
        text = text.rstrip() + "\n\n## Profiling findings (generated)\n\n" + block + "\n"
    doc.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", default="2023,2024")
    parser.add_argument("--docs", type=Path, default=None, help="docs/data.md to update")
    parser.add_argument("--cache-dir", type=Path, default=None)
    args = parser.parse_args()

    cache = args.cache_dir or get_settings().data_cache_dir
    seasons = [int(s) for s in args.seasons.split(",")]
    lines: list[str] = []
    frames: list[pd.DataFrame] = []
    version = None
    for season in seasons:
        src = fetch_pbp(season, cache)
        version = src.version
        df = pd.read_parquet(src.path)
        frames.append(df)
        lines += profile_season(src, df)

    players_path = download(get_settings().nflverse_players_url, cache / "players.parquet")
    lines += profile_players(players_path, frames)
    header = [f"Release `timestamp.json` at profiling time: `{version}`", ""]
    body = "\n".join(header + lines)
    print(body)
    if args.docs:
        write_section(args.docs, body)
        print(f"\nUpdated {args.docs}")


if __name__ == "__main__":
    main()
