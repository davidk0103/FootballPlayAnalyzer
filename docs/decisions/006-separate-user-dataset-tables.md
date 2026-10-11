# ADR 006: Separate tables for user uploads

- Status: Accepted
- Date: 2026-10-11

## Context

M3 lets signed-in users upload their own play-by-play CSV and analyze it with the same
metrics as the public nflverse data. Uploaded rows are private, have a different shape
(many optional columns, no player ids, free-form team codes), and are deleted when the
user deletes the upload. Public data is shared, carefully validated, and keyed on
nflverse ids.

## Decision

Store uploads in three new tables, never in `plays` / `rejected_rows`:

- `user_datasets`: one row per upload. Owner, display name, original filename (display
  only), size, SHA-256, detected delimiter, header, row count, the saved column mapping,
  status (`uploaded`, `validated`, `processing`, `ready`, `failed`), counts, warnings,
  error, job id, and `content_version`.
- `user_plays`: the normalized plays of one upload (`dataset_id` FK, `ON DELETE
  CASCADE`), with the columns the analytics need. Team codes are plain strings, not
  FKs to `teams`.
- `user_rejected_rows`: up to 1,000 rejected rows per upload with the row number,
  reason, and raw values, for review.

Analytics read through one interface, `resolve_source(session, season, dataset_id,
viewer)`, which returns either the public season or the viewer's ready upload as the
same DataFrame shape. The metric code does not know which one it got.

## Consequences

- Public queries and indexes are untouched; a bad upload cannot corrupt shared data.
- Deleting an upload is one `DELETE` (cascade), with no risk to public rows.
- Ownership is a single `user_id` check on `user_datasets`; another user's upload is a
  404 (not 403), so ids are not confirmable.
- Two schemas to migrate when the play shape changes. Accepted: uploads intentionally
  store a smaller column set.
- Upload analytics are cached with `cache_scope=upload:{id}` and `content_version` in the
  key, so a re-processed upload never serves stale numbers.

## Alternatives considered

- **One `plays` table with a nullable `owner_id`.** Every public query would need an
  extra predicate, team FKs would not fit free-form codes, and one missed filter leaks
  private data.
- **A schema per user.** Heavy to migrate and operate for a portfolio-scale app.
