# PlaybookIQ API (v1)

Base URL: `http://localhost:8317`. Interactive docs at `/docs`, schema at `/openapi.json`.

## Health

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health/live` | Process is up. Always `{"status": "ok"}`. |
| GET | `/health/ready` | 200 `{"status": "ok", "database": "ok", "redis": "ok"}` when the database answers, else 503. Redis is reported (`ok` / `unavailable`) but optional: analytics degrade to uncached. |

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

`team_a` / `team_b` accept a team abbreviation or id and must differ. `season` is
required. Shared filters (all optional):

| Param | Values | Meaning |
| --- | --- | --- |
| `season_type` | `REG`, `POST` | Regular season or playoffs. Omit for both. |
| `down` | `1`-`4`, repeatable | Down(s) to include. |
| `distance` | `short`, `medium`, `long` | Yards to go: 1-3, 4-7, 8+. |
| `field_zone` | `own_deep`, `own`, `opp`, `red_zone` | `yardline_100`: 80-99, 50-79, 21-49, 1-20. |
| `qtr` | `1`-`5`, repeatable | Quarter (5 = overtime). |
| `play_type` | `pass`, `run` | Scrimmage play type. |
| `side` | `offense`, `defense` | Team's plays on offense (default) or allowed on defense. |

### Caching

Both analytics endpoints are cached in Redis for 1 hour, keyed on the season's
dataset checksum, a per-season generation, and the canonical filters. Imports
invalidate their season automatically.

- Response header `X-Cache`: `HIT`, `MISS`, `BYPASS`, `DEGRADED` (Redis unreachable,
  served from PostgreSQL), or `DISABLED` (`CACHE_ENABLED=false`).
- `?no_cache=true` skips the cache (fresh result, not stored).

`GET /api/v1/cache/stats`:

```json
{"enabled": true, "available": true, "hits": 30, "misses": 10, "bypass": 1,
 "invalidations": 2, "hit_rate": 0.75, "degraded_errors_this_process": 0, "ttl_seconds": 3600}
```

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

The comparison endpoint returns `{"filters", "team_a", "team_b", "definitions", "dataset", "warnings"}`
where `team_a` / `team_b` each hold `team`, `sample`, `metrics`, and `warnings`, and
the top-level `warnings` repeats them prefixed with the team abbreviation
(`"KC: Sample under 30 plays"`). `filters` echoes every filter key, with `null`
for filters that were not set. `dataset` is the latest completed import for the season.

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

## Jobs

Background season imports. State lives in PostgreSQL; see
[architecture: job lifecycle](architecture.md#job-lifecycle) for the state machine.

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/jobs/import` | Queue an import. 202 new job, 200 idempotent replay, 409 conflict. |
| GET | `/api/v1/jobs` | Paginated, newest first. Query: `status`, `page`, `page_size` (max 100). |
| GET | `/api/v1/jobs/{id}` | One job. 404 if unknown, 422 if `id` is not a UUID. |
| GET | `/api/v1/jobs/{id}/attempts` | Execution attempts, oldest first. |
| POST | `/api/v1/jobs/{id}/cancel` | Cancel. 202 with the updated job; 409 `job_finished` if terminal. |

### Submit

```http
POST /api/v1/jobs/import
Idempotency-Key: 7c1e0d1a-5b8f-4e0b-9a43-2b7f1c9d0e11
Content-Type: application/json

{"season": 2024, "force": false}
```

- `season`: 1999-2100. `force`: re-import even if the file checksum is unchanged.
- `Idempotency-Key` header (or `idempotency_key` in the body), up to 200 chars.
  Generate one per user action and reuse it when retrying that request:
  - same key + same body: **200** with the original job and `Idempotent-Replayed: true`;
    nothing new is queued.
  - same key + different body: **409** `idempotency_key_reused`.
  - no key: each request is new.
- At most one active (`queued`, `running`, `retrying`, `cancel_requested`) import per
  season: otherwise **409** `duplicate_job` with `details.existing_job_id`.
- If the broker is unreachable the job is still accepted (202, `queued`) and published
  by the reaper once Redis is back.

### Job

```json
{
  "id": "bea5165a-dbb5-4879-86da-34da248087f5",
  "task_type": "import_season",
  "status": "succeeded",
  "params": {"season": 2024, "force": true},
  "user_id": null,
  "attempt_count": 1,
  "max_attempts": 4,
  "timeout_seconds": 900,
  "result": {"status": "imported", "stored": 43110, "rejected": 0, "games": 285,
             "row_count": 49492, "seconds": 8.25, "sha256": "3fd2...", "dataset_id": 2},
  "error": null,
  "created_at": "2026-10-10T22:46:58Z", "updated_at": "...",
  "started_at": "...", "finished_at": "...", "heartbeat_at": "...",
  "next_retry_at": null, "cancel_requested_at": null
}
```

`status` is one of `queued`, `running`, `retrying`, `cancel_requested`, `succeeded`,
`failed`, `cancelled`. `result.status` is `imported` or `skipped_duplicate` (same
checksum already imported). `user_id` is always `null` until accounts ship (M3).

### Attempt

```json
{"attempt_number": 1, "status": "failed", "worker": "worker@1ba3a81b761e:12",
 "error_type": "TransientJobError", "error": "...", "retry_delay_seconds": 1.42,
 "started_at": "...", "finished_at": "..."}
```

Attempt `status`: `running`, `succeeded`, `failed`, `cancelled`, or `lost` (the worker
died without recording an outcome).

### Cancel semantics

- `queued` / `retrying`: becomes `cancelled` immediately.
- `running`: becomes `cancel_requested`. The worker stops at its next chunk checkpoint
  (within about a second), rolls the import back, and marks it `cancelled`. If the
  import finishes first, the job ends `succeeded`.
- `cancel_requested`: no-op (202).
- Terminal: 409 `job_finished`.

Poll `GET /jobs/{id}` (the dashboard polls every 1.5s while jobs are active).

## Errors

```json
{"error": {"code": "not_found", "message": "Team 'XYZ' not found", "request_id": "..."}}
```

Some errors add a `details` object (for example `existing_job_id` on 409s).

| Status | Code | When |
| --- | --- | --- |
| 404 | `not_found` | Unknown team, game, job, or season with no data. |
| 409 | `duplicate_job` | An import for that season is already active. |
| 409 | `idempotency_key_reused` | Idempotency key was used with different parameters. |
| 409 | `job_finished` | Cancelling a job that already finished. |
| 422 | `validation_error` | Invalid filter value or missing required parameter. |
| 500 | `internal_error` | Unhandled error (details logged, not returned). |

Every response carries an `X-Request-ID` header (echoed if the client sent one).
