# ADR 011: Server-side CSV validation, preview, and column mapping

- Status: Accepted
- Date: 2026-10-11

## Context

Coaches export play-by-play from many tools, with different headers, delimiters, and
encodings. The app must accept those files, explain problems row by row, and never
trust the browser's view of the file (extension, MIME type, or client-side parsing).

## Decision

**Validate by content on the server**, in two stages.

1. **On upload** (`app/uploads/csvfile.py`, synchronous, whole file streamed once):
   UTF-8 required (BOM allowed); NUL bytes mean binary and are rejected; the delimiter
   is sniffed from `, ; \t |`; the header must be non-empty and unique; at most 100
   columns, 200,000 rows, and 1,000 characters per cell; every row must have the
   header's width. Each failure is a 422 with a specific code (`not_utf8`,
   `binary_file`, `ragged_rows`, `too_many_rows`, ...). An identical file (same
   SHA-256) already uploaded by the user is 409 `duplicate_upload` with its id. The
   response includes a 20-row preview and a **suggested mapping**.
2. **Mapping** (`app/uploads/mapping.py`, `normalize.py`): the user maps PlaybookIQ
   fields to their columns. Four fields are required (game, offense, defense, play
   type); the rest are optional and leave their metrics `n/a` when missing. Suggestions
   match header aliases ignoring case and punctuation (`Gn/Ls` to yards gained), using
   each column at most once. `POST /validate` dry-runs the mapping on the first 2,000
   rows and returns accepted/rejected counts, up to 50 example problems with the
   original values, and warnings (for example "success was derived from EPA").
   Processing applies the same `normalize()` to every row in chunks.

Row-level checks give reasons a person can act on ("Down must be a whole number from 1
to 4 (got '5')", "Offense and defense are the same team"). Rejected rows are stored for
review, never silently dropped.

**Formula injection.** Preview cells are rendered as text by React (never HTML), and any
CSV the app writes (report exports, see [ADR 012](012-csv-json-exports-and-print.md))
prefixes text cells starting with `= + - @ \t \r` with `'`.

## Consequences

- The same rules apply to every client; the UI's checks (extension, 25 MB, empty file)
  only save a round trip.
- Validation reads the file twice (inspect, then normalize). At the 25 MB / 200k row cap
  this is a few seconds and runs in the worker for processing.

## Alternatives considered

- **Parse in the browser and send JSON.** Faster feedback, but the server would still
  need to validate everything, and large files would strain low-end devices.
- **A fixed template only.** Simplest, but pushes the mapping work onto every coach.
