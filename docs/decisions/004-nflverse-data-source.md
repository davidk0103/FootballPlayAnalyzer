# ADR 004: nflverse play-by-play as the data source

- Status: Accepted (licensing follow-up open)
- Date: 2026-10-10

## Context

The app needs play-level NFL data with EPA, success, down/distance, and player IDs.

## Decision

Use the `pbp` release of [nflverse-data](https://github.com/nflverse/nflverse-data)
(parquet, one file per season), seasons 2023 and 2024 for M1. Player names and
positions come from the nflverse `players` release keyed on `gsis_id`.

## Rationale

- Free, well documented (372-field data dictionary), widely used.
- Precomputed EPA and success, so we do not build an expected-points model.
- Parquet is about 20 MB per season versus about 94 MB for CSV (requires `pyarrow`).

## Consequences

- Dataset version = release `timestamp.json` value + file SHA-256.
- nflverse `success` means `epa > 0`, not the classic down-based rule; metric
  definitions say so explicitly.
- Licensing: nflfastR code is MIT, but the nflverse-data README states no data
  license and the underlying data originates from the NFL. PlaybookIQ is a
  non-commercial portfolio project with attribution (see `docs/data.md`).
  Confirming the terms with nflverse remains an open follow-up.
