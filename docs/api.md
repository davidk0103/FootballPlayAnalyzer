# PlaybookIQ API (v1)

Base URL: `http://localhost:8317`. Interactive docs at `/docs`, schema at `/openapi.json`.

## Authentication, CSRF, and rate limits

Public analytics need no account. Uploads, saved reports, exports, and starting season
imports do. See [ADR 009](decisions/009-argon2-jwt-cookie-sessions.md).

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | `{"email", "password"}` (password 10-128 chars). 201 with the user, sets the session cookie. 409 `email_taken`. |
| POST | `/api/v1/auth/login` | 200 with the user, sets the cookie. 401 `invalid_credentials` (same message whether or not the email exists). |
| POST | `/api/v1/auth/logout` | 204, clears the cookie. |
| POST | `/api/v1/auth/logout-all` | 204, revokes every session of the user (bumps `token_version`). |
| GET | `/api/v1/auth/me` | The signed-in user (`id`, `email`, `is_admin`, `created_at`), else 401. |

- The session is a JWT in the `piq_session` cookie (`HttpOnly`, `SameSite=Lax`,
  `Secure` when `COOKIE_SECURE=true`), valid 12 hours.
- **Every POST/PUT/PATCH/DELETE must send `X-PlaybookIQ-CSRF: 1`**, signed in or not.
  Without it: 403 `csrf_failed`.
- Rate limits (429 `rate_limited` with `Retry-After`), see
  [ADR 010](decisions/010-redis-rate-limiter-with-fallback.md): login 30/min per IP and
  10/15 min per email; register 20/hour per IP; uploads 30/hour, report creation
  60/hour, and exports 60/hour per user.
- Private resources owned by someone else return **404**, not 403.

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

### Situational, efficiency, trends, tendencies (M3)

All accept the shared filters plus `week_min`, `week_max` (1-22), `opponent`
(abbreviation), `score_state` (`trailing_9plus`, `trailing_1_8`, `tied`,
`leading_1_8`, `leading_9plus`; the team's margin, one score = 1-8 points), and
`explosive_run_yards` / `explosive_pass_yards` (defaults 10 / 20). Instead of `season`,
pass **`dataset_id`** (one of your processed uploads, signed in) to analyze uploaded
data; an upload that is not `ready` is 409 `upload_not_ready`, and someone else's is 404.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/analytics/situational` | `group_by` = `down`, `distance`, `field_zone`, `qtr`, `score_state`, or `play_type`; optional `team` (omit for the whole league). Returns `overall` and `rows[]`, each with `plays`, `games`, `metrics`, and the league's `league` metrics for the same bucket (null without a team). |
| GET | `/api/v1/analytics/efficiency` | `team` required. `splits[]` for all plays, passing, and rushing, each with `metrics`, `league`, and `rank` (EPA/play among all teams under the same filters; defenses ranked lowest-first). |
| GET | `/api/v1/analytics/trends` | `team` required. `games[]`: per-game `metrics` with `week`, `opponent`, `plays`, and `league_epa_per_play` for that week. |
| GET | `/api/v1/teams/{team}/tendencies` | `down_distance[]` (pass rate, EPA, success by down x distance, with the league pass rate) and `third_down` (conversion, rank, average distance, conversions by penalty, `by_distance[]`). |

Every response carries `filters`, `definitions`, `dataset` (`kind` = `public` or
`upload`, with the upload's `id` and `name`), and `warnings` (small samples, upload
caveats such as "league values are computed across the teams in your upload").

### Players (M3)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/players` | Paginated search. `search` (2+ chars, name), `season` (only players with plays that season, ordered by plays), `position`. |
| GET | `/api/v1/players/{gsis_id}` | One player. |
| GET | `/api/v1/players/{gsis_id}/stats` | Shared filters. `passing`, `rushing`, `receiving` objects (counts as integers, rates as metric objects with numerator/denominator), `teams`, `sample`, `definitions`, and `limitations`. Public data only. |
| GET | `/api/v1/games/{game_id}/plays` | Paginated plays of one game, optional `play_type`. |

Yardage is nflverse's credited `passing_yards` / `rushing_yards` / `receiving_yards`
([ADR 013](decisions/013-additive-player-yards-migration.md)).

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

## Uploads (M3, signed in)

Private play-by-play CSVs. Flow: upload, map columns, validate, process (background
job), analyze with `dataset_id`. See [ADR 006](decisions/006-separate-user-dataset-tables.md),
[ADR 007](decisions/007-upload-storage-on-shared-volume.md), and
[ADR 011](decisions/011-server-side-csv-validation.md).

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/uploads/schema` | The mappable fields: `name`, `label`, `kind`, `description`, `required`. |
| POST | `/api/v1/uploads` | `multipart/form-data` with `file` and optional `name`. 201 with the upload detail (preview, suggested mapping, schema). 413 over 25 MB, 422 with a CSV code, 409 `duplicate_upload` (`details.existing_upload_id`). |
| GET | `/api/v1/uploads` | Your uploads, newest first (paginated). |
| GET | `/api/v1/uploads/{id}` | Detail: status, counts, seasons, warnings, `preview`, `suggested_mapping`, `schema_fields`, and the processing `job`. |
| POST | `/api/v1/uploads/{id}/validate` | `{"mapping": {"field": "column"}}`. Dry run on the first 2,000 rows: `valid`, `mapping_errors[]`, `checked_rows`, `accepted_rows`, `rejected_rows`, up to 50 `issues[]` (`row_number`, `reason`, original `values`), `warnings[]`. A valid mapping is saved and the status becomes `validated`. |
| POST | `/api/v1/uploads/{id}/process` | 202 with the `import_upload` job. `Idempotency-Key` supported. 409 `upload_not_validated`, `upload_busy`, or `upload_file_removed`. |
| DELETE | `/api/v1/uploads/{id}` | 204; deletes plays, rejected rows, and the file. 409 `upload_processing` while processing. |
| GET | `/api/v1/uploads/{id}/teams` | Teams in a ready upload with offense and defense play counts. |
| GET | `/api/v1/uploads/{id}/rejected` | Paginated rejected rows (first 1,000 are stored; `stored_limit`). |

Status: `uploaded` (needs mapping), `validated`, `processing`, `ready`, `failed`. A
failed or cancelled processing job turns the upload `failed` (or back to `validated` if
cancelled), and it can be processed again. CSV error codes (422): `empty_file`,
`no_delimiter`, `bad_header`, `too_many_columns`, `not_utf8`, `malformed_csv`,
`binary_file`, `ragged_rows`, `cell_too_long`, `too_many_rows`, `no_rows`.

## Reports and exports (M3, signed in)

Deterministic, rule-based scouting reports, saved per user. See
[ADR 012](decisions/012-csv-json-exports-and-print.md).

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/reports` | `{"team", "season"` or `"dataset_id", "title"?, "season_type"?, "week_min"?, "week_max"?, "opponent"?, "explosive_run_yards"?, "explosive_pass_yards"?}`. Checks access immediately, then 202 with a `pending` report and a `generate_report` job. `Idempotency-Key` supported. |
| GET | `/api/v1/reports` | Your reports (summaries), newest first. |
| GET | `/api/v1/reports/{id}` | The report: `status` (`pending`, `ready`, `failed`), `filters`, `report` (when ready), `exports[]`. |
| DELETE | `/api/v1/reports/{id}` | 204; also deletes export files. |
| POST | `/api/v1/reports/{id}/exports` | `{"format": "csv" \| "json"}`. 202 with a `pending` export. 409 `report_not_ready`. |
| GET | `/api/v1/reports/{id}/exports/{export_id}` | Export status and `download_url` when ready. |
| GET | `/api/v1/reports/{id}/exports/{export_id}/download` | The file as an attachment (`nosniff`, `no-store`). 409 `export_not_ready`. |

A ready `report` contains `offense` and `defense` (`plays`, `games`, `metrics[]` with
`value`, `league_value`, `difference`, `rank`, `of`, `better`, numerator/denominator;
`third_down`; `red_zone` and `league_red_zone`), `tendencies[]`, `findings[]`,
`top_players[]` (public data only), `definitions`, `warnings`, and `limitations`.

**Finding rules** (same inputs, same report): ranks need at least 4 teams; a metric in
the top third of the league is a `strength`, the bottom third a `weakness`; a pass rate
at least 5 points from the league is a `tendency`. A metric only qualifies with at least
30 plays on that side (and 20 third downs for third-down conversion).

## Jobs

Background work: season imports (`import_season`, admins only), upload processing
(`import_upload`), report generation (`generate_report`), and exports
(`export_report`). State lives in PostgreSQL; see
[architecture: job lifecycle](architecture.md#job-lifecycle) and
[ADR 008](decisions/008-generic-owner-scoped-jobs.md). `GET /jobs` lists season imports
plus the viewer's own jobs; other users' jobs are 404. Cancelling needs ownership (or
admin for season imports).

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/jobs/import` | Queue a season import (admin). 202 new job, 200 idempotent replay, 409 conflict, 403 `admin_required`. |
| GET | `/api/v1/jobs` | Paginated, newest first. Query: `status`, `task_type`, `page`, `page_size` (max 100). |
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
checksum already imported). `user_id` is the submitting user. `progress` is
`{"stage", "done", "total"}` while running (for uploads: `reading`, `validating`,
`storing`).

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
| 401 | `unauthorized` | Sign-in required (or the session expired / was revoked). |
| 401 | `invalid_credentials` | Wrong email or password. |
| 403 | `csrf_failed` | Unsafe request without `X-PlaybookIQ-CSRF: 1`. |
| 403 | `admin_required` | Starting or cancelling a season import as a non-admin. |
| 404 | `not_found` | Unknown team, game, job, player, or season with no data; or someone else's upload, report, export, or job. |
| 409 | `duplicate_job` | A job for the same target (season, upload, report) is already active. |
| 409 | `idempotency_key_reused` | Idempotency key was used with different parameters. |
| 409 | `job_finished` | Cancelling a job that already finished. |
| 409 | `email_taken` | Registering an email that already has an account. |
| 409 | `duplicate_upload` | You already uploaded an identical file (`details.existing_upload_id`). |
| 409 | `upload_not_ready` / `upload_not_validated` / `upload_busy` / `upload_processing` / `upload_file_removed` | Upload is in the wrong state for the action. |
| 409 | `report_not_ready` / `export_not_ready` | Report or export is still pending or failed. |
| 413 | `payload_too_large` | Upload over 25 MB. |
| 422 | `validation_error` | Invalid filter value or missing required parameter. |
| 422 | CSV codes (`not_utf8`, `ragged_rows`, ...) | The uploaded file is not a usable CSV (see Uploads). |
| 429 | `rate_limited` | Too many requests; `Retry-After` says when to retry. |
| 500 | `internal_error` | Unhandled error (details logged, not returned). |

Every response carries an `X-Request-ID` header (echoed if the client sent one).
