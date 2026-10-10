# PlaybookIQ API (v1)

Base URL: `http://localhost:8317`. Interactive docs at `/docs`, schema at `/openapi.json`.

## Health

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health/live` | Process is up. Always `{"status": "ok"}`. |
| GET | `/health/ready` | Database reachable. 200 `{"status": "ok"}` or 503. |

## Seasons

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/seasons` | Seasons with imported data: `season`, `plays`, `games`, `dataset_version`, `sha256`. Feeds the season picker. |

## Teams

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/teams` | All teams (`id`, `abbreviation`, `name`, `conference`, `division`). |
| GET | `/api/v1/teams/{team_id}` | One team. 404 if unknown. |
| GET | `/api/v1/teams/{team_id}/stats` | Analytics envelope for one team. Query: `season` (required), `side=offense\|defense` (default offense), plus the shared filters below. |

## Games

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/games` | Paginated. Query: `season`, `week`, `team` (abbreviation), `page` (default 1), `page_size` (default 25, max 100). |
| GET | `/api/v1/games/{game_id}` | One game by internal id, with play count. 404 if unknown. |

Paginated response: `{"items": [...], "page": 1, "page_size": 25, "total": 285}`.

## Analytics

`GET /api/v1/analytics/team-comparison?team_a=KC&team_b=BUF&season=2024`

`team_a` / `team_b` accept a team abbreviation. Shared filters (all optional):

| Param | Values | Meaning |
| --- | --- | --- |
| `season_type` | `REG`, `POST` | Regular season or playoffs. Omit for both. |
| `down` | `1`-`4`, repeatable | Down(s) to include. |
| `distance` | `short`, `medium`, `long` | Yards to go: 1-3, 4-7, 8+. |
| `field_zone` | `own_deep`, `own`, `opp`, `red_zone` | `yardline_100`: 80-99, 50-79, 21-49, 1-20. |
| `qtr` | `1`-`5`, repeatable | Quarter (5 = overtime). |
| `play_type` | `pass`, `run` | Scrimmage play type. |
| `side` | `offense`, `defense` | Team's plays on offense (default) or allowed on defense. |

### Envelope

Every analytics response (team stats, and each team in a comparison) uses:

```json
{
  "team": {"id": 16, "abbreviation": "KC", "name": "Kansas City Chiefs"},
  "filters": {"season": 2024, "side": "offense", "down": [3]},
  "sample": {"plays": 214, "games": 17},
  "metrics": {
    "epa_per_play": {"value": 0.08, "numerator": 17.1, "denominator": 214}
  },
  "definitions": {"epa_per_play": "Sum of EPA / scrimmage plays with EPA ..."},
  "dataset": {"source": "nflverse pbp", "version": "...", "sha256": "..."},
  "warnings": ["Sample under 30 plays"]
}
```

The comparison endpoint returns `{"filters", "team_a", "team_b", "definitions", "datasets", "warnings"}`
where `team_a` / `team_b` each hold `team`, `sample`, `metrics`, and `warnings`.

Rules:

- A metric whose denominator is 0 returns `"value": null` and a warning. Never 0.
- Samples under 30 plays add a warning.

### Metrics (M1)

| Key | Definition |
| --- | --- |
| `epa_per_play` | Sum of EPA / scrimmage plays with non-null EPA. |
| `success_rate` | Plays with `epa > 0` / scrimmage plays with non-null EPA (nflverse definition). |
| `yards_per_play` | Sum of `yards_gained` / scrimmage plays. |
| `pass_rate` | Pass plays (incl. sacks, scrambles) / scrimmage plays. |
| `third_down_conversion_rate` | Third-down plays converted / third-down plays. |
| `explosive_play_rate` | Runs of 10+ yards or passes of 20+ yards / scrimmage plays. |
| `turnovers_per_game` | (Interceptions + fumbles lost) / games. |

Scrimmage plays = `play_type` in (pass, run), excluding `no_play`, QB kneels,
spikes, two-point attempts, and plays nflverse marks as deleted. See `docs/data.md`.

## Errors

```json
{"error": {"code": "not_found", "message": "Team 'XYZ' not found", "request_id": "..."}}
```

| Status | Code | When |
| --- | --- | --- |
| 404 | `not_found` | Unknown team, game, or season with no data. |
| 422 | `validation_error` | Invalid filter value or missing required parameter. |
| 500 | `internal_error` | Unhandled error (details logged, not returned). |

Every response carries an `X-Request-ID` header (echoed if the client sent one).
