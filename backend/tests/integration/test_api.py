from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import create_app

pytestmark = pytest.mark.integration

# Reference values computed directly from the raw fixture parquet with pandas
# (pass/run, excluding two-point tries), independent of the app code.
DET_OFFENSE = {
    "plays": 66,
    "epa_sum": 3.0899,
    "successes": 27,
    "yards": 371,
    "passes": 35,
    "third_downs": 14,
    "third_converted": 5,
    "explosive": 6,
    "turnovers": 1,
}
KC_OFFENSE_PLAYS = 62


def _client_for(session: Session) -> httpx.AsyncClient:
    app = create_app()

    def override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(seeded_session: Session) -> AsyncIterator[httpx.AsyncClient]:
    async with _client_for(seeded_session) as c:
        yield c


@pytest.fixture
async def empty_client(db_session: Session) -> AsyncIterator[httpx.AsyncClient]:
    async with _client_for(db_session) as c:
        yield c


async def test_health(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "database": "ok", "redis": "ok"}


async def test_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health/live", headers={"X-Request-ID": "abc123"})
    assert resp.headers["X-Request-ID"] == "abc123"


async def test_list_and_get_teams(client: httpx.AsyncClient) -> None:
    teams = (await client.get("/api/v1/teams")).json()
    assert len(teams) == 32
    det = next(t for t in teams if t["abbreviation"] == "DET")
    assert det == {
        "id": det["id"],
        "abbreviation": "DET",
        "name": "Detroit Lions",
        "conference": "NFC",
        "division": "North",
    }
    by_id = (await client.get(f"/api/v1/teams/{det['id']}")).json()
    by_abbr = (await client.get("/api/v1/teams/det")).json()
    assert by_id == by_abbr == det


async def test_unknown_team_is_404_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/teams/XYZ", headers={"X-Request-ID": "req-1"})
    assert resp.status_code == 404
    assert resp.json() == {
        "error": {"code": "not_found", "message": "Team 'XYZ' not found", "request_id": "req-1"}
    }


async def test_seasons(client: httpx.AsyncClient) -> None:
    seasons = (await client.get("/api/v1/seasons")).json()
    assert len(seasons) == 1
    assert seasons[0]["season"] == 2023
    assert seasons[0]["games"] == 2
    assert seasons[0]["plays"] == 309


async def test_games_pagination_and_filters(client: httpx.AsyncClient) -> None:
    page = (await client.get("/api/v1/games", params={"season": 2023, "page_size": 1})).json()
    assert page["total"] == 2
    assert page["page_size"] == 1
    assert len(page["items"]) == 1

    kc = (await client.get("/api/v1/games", params={"team": "KC"})).json()
    assert kc["total"] == 1
    game = kc["items"][0]
    assert game["external_game_id"] == "2023_01_DET_KC"
    assert game["home_team"]["abbreviation"] == "KC"
    assert game["away_team"]["abbreviation"] == "DET"
    assert game["game_date"] == "2023-09-07"

    detail = (await client.get(f"/api/v1/games/{game['id']}")).json()
    assert detail["play_count"] > 0

    assert (await client.get("/api/v1/games/999999")).status_code == 404
    too_big = await client.get("/api/v1/games", params={"page_size": 101})
    assert too_big.status_code == 422
    assert too_big.json()["error"]["code"] == "validation_error"


async def test_team_stats_matches_reference(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/teams/DET/stats", params={"season": 2023})
    assert resp.status_code == 200
    body = resp.json()
    ref = DET_OFFENSE
    m = body["metrics"]
    assert body["sample"] == {"plays": ref["plays"], "games": 1}
    assert m["epa_per_play"]["numerator"] == pytest.approx(ref["epa_sum"], abs=1e-4)
    assert m["epa_per_play"]["denominator"] == ref["plays"]
    assert m["epa_per_play"]["value"] == pytest.approx(ref["epa_sum"] / ref["plays"], abs=1e-4)
    assert m["success_rate"]["numerator"] == ref["successes"]
    assert m["yards_per_play"]["numerator"] == ref["yards"]
    assert m["pass_rate"]["numerator"] == ref["passes"]
    assert m["third_down_conversion_rate"]["numerator"] == ref["third_converted"]
    assert m["third_down_conversion_rate"]["denominator"] == ref["third_downs"]
    assert m["explosive_play_rate"]["numerator"] == ref["explosive"]
    assert m["turnovers_per_game"]["value"] == ref["turnovers"]
    assert set(body["definitions"]) == set(m)
    assert body["dataset"]["source"] == "nflverse pbp"
    assert body["dataset"]["version"] == "test"
    assert body["warnings"] == []


async def test_team_stats_defense_side(client: httpx.AsyncClient) -> None:
    body = (
        await client.get("/api/v1/teams/DET/stats", params={"season": 2023, "side": "defense"})
    ).json()
    assert body["sample"]["plays"] == KC_OFFENSE_PLAYS
    assert body["filters"]["side"] == "defense"


async def test_comparison(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/analytics/team-comparison",
        params={"team_a": "DET", "team_b": "KC", "season": 2023},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_a"]["team"]["abbreviation"] == "DET"
    assert body["team_b"]["team"]["abbreviation"] == "KC"
    assert body["team_a"]["sample"]["plays"] == DET_OFFENSE["plays"]
    assert body["team_b"]["sample"]["plays"] == KC_OFFENSE_PLAYS
    assert body["filters"]["season"] == 2023


async def test_comparison_filters_and_small_sample_warning(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/analytics/team-comparison",
        params=[
            ("team_a", "DET"),
            ("team_b", "KC"),
            ("season", "2023"),
            ("down", "3"),
            ("play_type", "pass"),
        ],
    )
    body = resp.json()
    assert body["filters"]["down"] == [3]
    assert body["filters"]["play_type"] == "pass"
    det = body["team_a"]
    assert 0 < det["sample"]["plays"] < DET_OFFENSE["third_downs"] + 1
    assert det["metrics"]["pass_rate"]["value"] == 1.0
    assert "Sample under 30 plays" in det["warnings"]
    assert "DET: Sample under 30 plays" in body["warnings"]


async def test_comparison_empty_filter_returns_nulls(client: httpx.AsyncClient) -> None:
    body = (
        await client.get(
            "/api/v1/analytics/team-comparison",
            params={"team_a": "DET", "team_b": "KC", "season": 2023, "qtr": 5},
        )
    ).json()
    det = body["team_a"]
    assert det["sample"] == {"plays": 0, "games": 0}
    assert all(metric["value"] is None for metric in det["metrics"].values())
    assert det["warnings"] == ["No plays match these filters"]


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"team_a": "DET", "team_b": "DET", "season": 2023}, "must be different"),
        ({"team_a": "DET", "team_b": "KC", "season": 2023, "down": 5}, "down must be"),
        ({"team_a": "DET", "team_b": "KC", "season": 2023, "distance": "far"}, "distance"),
        ({"team_a": "DET", "team_b": "KC"}, "season"),
    ],
)
async def test_comparison_validation_errors(
    client: httpx.AsyncClient, params: dict[str, object], message: str
) -> None:
    resp = await client.get("/api/v1/analytics/team-comparison", params=params)  # type: ignore[arg-type]
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    assert message in error["message"]


async def test_comparison_unknown_team_and_season(client: httpx.AsyncClient) -> None:
    unknown = await client.get(
        "/api/v1/analytics/team-comparison",
        params={"team_a": "DET", "team_b": "ZZZ", "season": 2023},
    )
    assert unknown.status_code == 404
    no_season = await client.get(
        "/api/v1/analytics/team-comparison",
        params={"team_a": "DET", "team_b": "KC", "season": 2010},
    )
    assert no_season.status_code == 404
    assert no_season.json()["error"]["message"] == "No imported data for season 2010"


async def test_empty_database(empty_client: httpx.AsyncClient) -> None:
    assert (await empty_client.get("/api/v1/teams")).json() == []
    assert (await empty_client.get("/api/v1/seasons")).json() == []
