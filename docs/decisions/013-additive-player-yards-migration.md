# ADR 013: Additive migration for official player yardage

- Status: Accepted
- Date: 2026-10-11

## Context

The player explorer reports passing, rushing, and receiving yards. `yards_gained` is the
play's net yardage, which differs from the yards credited to players (laterals, sack
yardage, fumble returns). nflverse provides the credited values as `passing_yards`,
`rushing_yards`, and `receiving_yards`, plus `pass_attempt`, `rush_attempt`, and
`incomplete_pass` flags. The existing `plays` table did not store them.

## Decision

- Migration `0003` **adds six nullable columns** to `plays`. No column is changed or
  dropped, so it is safe to apply to a database with data, and `downgrade` simply drops
  them.
- Ingestion reads and stores the new columns. Nullable stays nullable: a missing value
  is `NULL`, never 0.
- Existing databases backfill with a forced re-import (`make ingest SEASONS=2023,2024`
  with `--force`, or the Jobs page with "force"). A season imported before the migration
  has `NULL` yardage, and player stats show `n/a` instead of wrong numbers.
- The test fixture was regenerated from the real 2023 file so tests exercise real
  values.

## Consequences

- Player totals match nflverse's credited yardage (within the occasional later
  correction, which the player page lists as a limitation).
- Players are not attributed fumbles (no fumbling-player id is stored); stated in the
  limitations.

## Alternatives considered

- **Compute player yards from `yards_gained`.** Wrong for sacks, laterals, and returns.
- **A separate `player_plays` table.** Normalized, but adds joins to every query for no
  current benefit.
