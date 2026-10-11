"""M3 analytics endpoints against the ingested fixture (ARI@WAS and DET@KC, 2023 week 1).

Reference values were computed directly from the raw fixture parquet with pandas,
independent of the app code; Goff's line also matches the official box score.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.orm import Session

from tests.integration.conftest import api_client

pytestmark = pytest.mark.integration

GOFF = "00-0033106"
MAHOMES = "00-0033873"


@pytest.fixture
async def client(seeded_session: Session) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(seeded_session) as c:
        yield c


def _envelope(body: dict[str, object]) -> None:
    for key in ("filters", "definitions", "dataset", "warnings"):
        assert key in body


async def test_situational_by_down_matches_reference(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/analytics/situational?season=2023&team=DET&group_by=down")
    assert resp.status_code == 200
    body = resp.json()
    _envelope(body)
    rows = {r["key"]: r for r in body["rows"]}
    assert [rows[k]["plays"] for k in ("1", "2", "3")] == [26, 23, 14]
    assert rows["3"]["metrics"]["pass_rate"]["numerator"] == 11
    assert rows["4"]["plays"] == 3
    assert rows["4"]["metrics"]["epa_per_play"]["value"] is not None
    assert body["overall"]["plays"] == 66
    # League bucket includes both games' offenses.
    assert rows["1"]["league"]["pass_rate"]["denominator"] > rows["1"]["plays"]
    assert any("Small samples" in w for w in body["warnings"])


async def test_score_state_uses_the_teams_perspective(client: httpx.AsyncClient) -> None:
    offense = await client.get(
        "/api/v1/analytics/situational?season=2023&team=DET&group_by=score_state"
    )
    rows = {r["key"]: r["plays"] for r in offense.json()["rows"]}
    assert rows["tied"] == 37
    assert rows["trailing_1_8"] + rows["trailing_9plus"] == 21
    assert rows["leading_1_8"] + rows["leading_9plus"] == 8

    defense = await client.get(
        "/api/v1/analytics/situational?season=2023&team=DET&side=defense&group_by=score_state"
    )
    d_rows = {r["key"]: r["plays"] for r in defense.json()["rows"]}
    # KC trailing on offense == DET leading on defense.
    assert d_rows["leading_1_8"] + d_rows["leading_9plus"] == 20


async def test_league_wide_situational_has_no_league_column(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/analytics/situational?season=2023&group_by=qtr")).json()
    assert body["team"] is None
    assert all(r["league"] is None for r in body["rows"])
    assert [r["label"] for r in body["rows"]] == ["Q1", "Q2", "Q3", "Q4", "Overtime"]


async def test_efficiency_splits_with_league_and_rank(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/analytics/efficiency?season=2023&team=DET")).json()
    _envelope(body)
    splits = {s["key"]: s for s in body["splits"]}
    assert splits["all"]["plays"] == 66
    assert splits["pass"]["plays"] == 35
    assert splits["pass"]["plays"] + splits["run"]["plays"] == 66
    assert "pass_rate" not in splits["pass"]["metrics"]
    rank = splits["all"]["rank"]
    assert rank["of"] == 4
    assert 1 <= rank["rank"] <= 4
    assert rank["better"] == "higher"
    defense = (
        await client.get("/api/v1/analytics/efficiency?season=2023&team=DET&side=defense")
    ).json()
    assert defense["splits"][0]["rank"]["better"] == "lower"


async def test_trends_one_point_per_game(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/analytics/trends?season=2023&team=KC")).json()
    assert len(body["games"]) == 1
    game = body["games"][0]
    assert game["opponent"] == "DET"
    assert game["week"] == 1
    assert game["league_epa_per_play"] is not None


async def test_tendencies_and_third_downs(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/teams/DET/tendencies?season=2023")).json()
    _envelope(body)
    third = body["third_down"]
    assert third["plays"] == 14
    assert third["conversion_rate"]["numerator"] == 5
    assert third["pass_rate"]["numerator"] == 11
    assert sum(b["plays"] for b in third["by_distance"]) == 14
    assert third["avg_yards_to_go"] is not None
    assert len(body["down_distance"]) == 12
    first_downs = [c for c in body["down_distance"] if c["down"] == 1]
    assert sum(c["plays"] for c in first_downs) == 26


async def test_filters_week_opponent_and_thresholds(client: httpx.AsyncClient) -> None:
    vs_kc = await client.get(
        "/api/v1/analytics/situational?season=2023&team=DET&opponent=kc&week_min=1&week_max=1"
    )
    assert vs_kc.json()["overall"]["plays"] == 66
    assert vs_kc.json()["filters"]["opponent"] == "KC"
    vs_ari = await client.get("/api/v1/analytics/situational?season=2023&team=DET&opponent=ARI")
    assert vs_ari.json()["overall"]["plays"] == 0
    assert "No plays match these filters" in vs_ari.json()["warnings"]

    default = (await client.get("/api/v1/teams/DET/stats?season=2023")).json()
    loose = (
        await client.get(
            "/api/v1/teams/DET/stats?season=2023&explosive_run_yards=5&explosive_pass_yards=10"
        )
    ).json()
    assert (
        loose["metrics"]["explosive_play_rate"]["numerator"]
        > default["metrics"]["explosive_play_rate"]["numerator"]
    )
    assert loose["filters"]["explosive_run_yards"] == 5
    assert "custom values" in loose["definitions"]["explosive_play_rate"]


async def test_filter_validation(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/analytics/situational")).status_code == 422
    bad_weeks = await client.get("/api/v1/analytics/situational?season=2023&week_min=5&week_max=2")
    assert bad_weeks.status_code == 422
    bad_group = await client.get("/api/v1/analytics/situational?season=2023&group_by=formation")
    assert bad_group.status_code == 422
    too_big = await client.get("/api/v1/teams/DET/stats?season=2023&explosive_run_yards=500")
    assert too_big.status_code == 422
    missing = await client.get("/api/v1/analytics/efficiency?season=2023&team=ZZZ")
    assert missing.status_code == 404
    no_data = await client.get("/api/v1/analytics/efficiency?season=2019&team=DET")
    assert no_data.status_code == 404


async def test_player_search_and_stats(client: httpx.AsyncClient) -> None:
    page = (await client.get("/api/v1/players?search=goff&season=2023")).json()
    assert [p["id"] for p in page["items"]] == [GOFF]
    assert page["items"][0]["season_plays"] > 30

    all_qbs = (await client.get("/api/v1/players?season=2023&position=qb")).json()
    assert {p["id"] for p in all_qbs["items"]} >= {GOFF, MAHOMES}

    assert (await client.get(f"/api/v1/players/{GOFF}")).json()["name"] == "Jared Goff"
    stats = (await client.get(f"/api/v1/players/{GOFF}/stats?season=2023")).json()
    _envelope(stats)
    passing = stats["passing"]
    assert passing["pass_attempts"] == 35
    assert passing["completions"] == 22
    assert passing["passing_yards"] == 253
    assert passing["sacks"] == 1
    assert passing["interceptions"] == 0
    assert passing["completion_rate"]["value"] == pytest.approx(22 / 35, abs=1e-4)
    assert stats["teams"] == ["DET"]
    assert stats["limitations"]

    mahomes = (await client.get(f"/api/v1/players/{MAHOMES}/stats?season=2023")).json()
    assert (mahomes["passing"]["pass_attempts"], mahomes["passing"]["interceptions"]) == (39, 1)


async def test_player_errors(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/players/00-0000000")).status_code == 404
    assert (await client.get("/api/v1/players?search=a")).status_code == 422
    assert (await client.get("/api/v1/players?page_size=500")).status_code == 422
    none = (await client.get(f"/api/v1/players/{GOFF}/stats?season=2023&opponent=ARI")).json()
    assert none["sample"]["plays"] == 0
    assert none["passing"]["completion_rate"]["value"] is None


async def test_game_plays_paginated(client: httpx.AsyncClient) -> None:
    games = (await client.get("/api/v1/games?season=2023&team=DET")).json()
    game_id = games["items"][0]["id"]
    first = (await client.get(f"/api/v1/games/{game_id}/plays?page_size=10")).json()
    assert first["game"]["id"] == game_id
    assert len(first["items"]) == 10
    assert first["total"] > 100
    ids = [p["play_id"] for p in first["items"]]
    assert ids == sorted(ids)
    passes = (await client.get(f"/api/v1/games/{game_id}/plays?play_type=pass")).json()
    assert all(p["play_type"] == "pass" for p in passes["items"])
    assert (await client.get("/api/v1/games/999999/plays")).status_code == 404


async def test_new_analytics_are_cached(client: httpx.AsyncClient) -> None:
    url = "/api/v1/teams/DET/tendencies?season=2023"
    assert (await client.get(url)).headers["X-Cache"] == "MISS"
    assert (await client.get(url)).headers["X-Cache"] == "HIT"
