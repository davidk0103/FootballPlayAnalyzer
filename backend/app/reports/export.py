"""Render a stored report as CSV or JSON.

CSV formula injection: spreadsheet apps execute cells that start with ``=``, ``+``,
``-``, ``@``, tab, or carriage return. Every text cell that starts with one of those is
prefixed with a single quote, so it is shown as text. Numbers are written as numbers
(a negative number is data, not a formula). Text cells include user-controlled values
such as the report title and dataset name.
"""

import csv
import io
import json
from collections.abc import Iterable
from typing import Any

from app.reports.contracts import ScoutingReportOut

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
CSV_HEADER = (
    "section",
    "side",
    "item",
    "label",
    "value",
    "league_value",
    "difference",
    "rank",
    "of",
    "numerator",
    "denominator",
)


def safe_cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return value
    text = str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def _rows(title: str, report: ScoutingReportOut) -> Iterable[tuple[object, ...]]:
    meta = {
        "title": title,
        "team": report.team.abbreviation,
        "team_name": report.team.name,
        "dataset": report.dataset.name or report.dataset.source,
        "dataset_version": report.dataset.version,
        "season": report.filters.season,
        "generated_at": report.generated_at.isoformat(),
    }
    for key, value in meta.items():
        yield ("meta", "", key, key, value, None, None, None, None, None, None)
    for side in (report.offense, report.defense):
        yield ("sample", side.side, "plays", "Scrimmage plays", side.plays, *([None] * 6))
        yield ("sample", side.side, "games", "Games", side.games, *([None] * 6))
        for m in side.metrics:
            yield (
                "metric",
                side.side,
                m.name,
                m.label,
                m.value,
                m.league_value,
                m.difference,
                m.rank,
                m.of,
                m.numerator,
                m.denominator,
            )
        td = side.third_down
        for bucket in td.by_distance:
            yield (
                "third_down",
                side.side,
                bucket.distance,
                f"3rd and {bucket.distance}: conversion rate",
                bucket.conversion_rate.value,
                bucket.league_conversion_rate.value,
                None,
                None,
                None,
                bucket.conversion_rate.numerator,
                bucket.conversion_rate.denominator,
            )
        rz, lrz = side.red_zone, side.league_red_zone
        for name in ("epa_per_play", "success_rate", "touchdown_rate"):
            mine, league = getattr(rz, name), getattr(lrz, name)
            yield (
                "red_zone",
                side.side,
                name,
                f"Red zone {name.replace('_', ' ')}",
                mine.value,
                league.value,
                None,
                None,
                None,
                mine.numerator,
                mine.denominator,
            )
    for cell in report.tendencies:
        yield (
            "tendency",
            "offense",
            f"down{cell.down}_{cell.distance}",
            f"Pass rate on {cell.down} and {cell.distance}",
            cell.pass_rate.value,
            cell.league_pass_rate.value,
            None,
            None,
            None,
            cell.pass_rate.numerator,
            cell.pass_rate.denominator,
        )
    for p in report.top_players:
        yield (
            "leader",
            "offense",
            p.category,
            p.name or p.player_id,
            p.yards,
            *([None] * 4),
            p.volume,
            None,
        )
    for f in report.findings:
        yield ("finding", f.side, f.metric, f.text, f.kind, *([None] * 6))
    for w in report.warnings:
        yield ("warning", "", "", w, *([None] * 7))
    for limitation in report.limitations:
        yield ("limitation", "", "", limitation, *([None] * 7))


def render_csv(title: str, report: ScoutingReportOut) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for row in _rows(title, report):
        writer.writerow([safe_cell(v) for v in row])
    return buf.getvalue().encode("utf-8-sig")


def render_json(title: str, report: ScoutingReportOut) -> bytes:
    body: dict[str, Any] = {"title": title, **report.model_dump(mode="json")}
    return json.dumps(body, indent=2, sort_keys=False).encode()
