# ADR 012: CSV and JSON report exports plus a print-friendly page, no PDF

- Status: Accepted
- Date: 2026-10-11

## Context

Saved scouting reports need to leave the app: into a spreadsheet, into other code, or
onto paper for a meeting. Server-side PDF rendering needs a headless browser or a layout
library, which is a heavy dependency for one feature.

## Decision

- **CSV export** (`app/reports/export.py`): UTF-8 with BOM (so Excel opens it
  correctly), long format with the columns `section, side, item, label, value,
  league_value, difference, rank, of, numerator, denominator`. Numbers are written raw.
  Text cells beginning with `= + - @ \t \r` are prefixed with `'` (formula-injection
  protection).
- **JSON export**: the same `ScoutingReportOut` the API returns, pretty-printed.
- Exports are built by an `export_report` background job ([ADR 008](008-generic-owner-scoped-jobs.md))
  into `exports/` ([ADR 007](007-upload-storage-on-shared-volume.md)). The download
  endpoint is owner-only and sends `Content-Disposition: attachment` with a slugged
  filename, `X-Content-Type-Options: nosniff`, and `Cache-Control: no-store`.
- **Print**: the report page has a Print button (`window.print()`). Navigation, export
  controls, and status badges are hidden with Tailwind `print:` variants and cards avoid
  page breaks, so the browser's "Save as PDF" gives a clean document.

## Consequences

- No new rendering dependency; the browser handles PDF.
- Exports are snapshots: regenerating a report creates a new one.
- Print layout depends on the browser; acceptable for meeting handouts.

## Alternatives considered

- **Server-side PDF (WeasyPrint, Playwright).** Large dependency and container size for
  output the browser can already produce.
- **Synchronous export.** Fine for current sizes, but the job model already exists and
  keeps request latency flat.
