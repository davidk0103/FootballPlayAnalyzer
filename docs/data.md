# PlaybookIQ data

> Draft. The "Profiling findings" section is filled in by
> `backend/scripts/profile_pbp.py` against the real 2023 and 2024 files.

## Source

- [nflverse-data](https://github.com/nflverse/nflverse-data) release `pbp`,
  file `play_by_play_<season>.parquet`. Seasons 2023 and 2024 in M1.
- Version marker: the release's `timestamp.json` plus each file's SHA-256.
- Players: release `players`, file `players.parquet`, keyed on `gsis_id`.
- Field definitions: the nflreadr data dictionary (`dictionary_pbp.csv`, 372 fields).

## Attribution and licensing

Play-by-play data courtesy of the nflverse project (nflfastR / nflreadr). The
nflfastR code is MIT licensed; the nflverse-data repository does not state an
explicit data license and the underlying data originates from NFL sources.
PlaybookIQ uses the data for non-commercial, educational portfolio purposes
with attribution. Confirming the terms with nflverse is an open follow-up.

## Columns used

- IDs and context: `game_id`, `play_id`, `season`, `season_type`, `week`,
  `game_date`, `home_team`, `away_team`, `posteam`, `defteam`.
- Situation: `qtr`, `game_seconds_remaining`, `down`, `ydstogo`, `yardline_100`,
  `score_differential`.
- Outcome: `play_type`, `yards_gained`, `epa`, `success`.
- Players: `passer_player_id`, `rusher_player_id`, `receiver_player_id`.
- Indicators: `touchdown`, `interception`, `fumble_lost`, `complete_pass`, `sack`,
  `pass`, `rush`, `first_down`, `penalty`, `third_down_converted`,
  `two_point_attempt`, `qb_kneel`, `qb_spike`, `aborted_play`, `play_deleted`.

## Known definitions

- `success` is `epa > 0` (nflverse), not the classic 40/60/100% rule.
- `play_type == "pass"` includes sacks; `"run"` includes scrambles.
- `play_type == "no_play"` marks plays wiped out by penalty.
- `yards_gained` excludes yards from fumble recoveries and laterals.
- `play_id` is unique only within a game; natural key is `(game_id, play_id)`.

## Missing values

Nullable source columns are stored as `NULL`. Ingestion never writes 0 for a
missing value, and a metric with a zero denominator returns `null`.
