# ADR 002: pandas aggregation over SQL aggregation for M1

- Status: Accepted (to be revisited with benchmarks in M4)
- Date: 2026-10-10

## Context

Team metrics (EPA per play, success rate, third-down conversion, explosive-play
rate) can be computed either with SQL `GROUP BY` queries or by pulling filtered
rows into pandas.

## Decision

For M1, repositories fetch only the filtered columns and rows a request needs,
and pure pandas functions in `app/analytics/` compute the metrics.

## Rationale

- Pure functions are trivially unit tested with hand-built DataFrames that have
  known answers, including zero-denominator and NULL-EPA cases.
- Metric definitions live in one readable place rather than spread across SQL strings.
- Data volume is small: a team-season is about 1,050 regular-season offensive scrimmage
  plays (measured in `docs/data.md`).

## Consequences

- Each request transfers rows over the wire; fine at this scale.
- M4 benchmarks this approach against SQL aggregation and records the result in
  `docs/benchmarks.md`. If SQL wins meaningfully, the repository can switch
  while the analytics tests stay as the specification.
