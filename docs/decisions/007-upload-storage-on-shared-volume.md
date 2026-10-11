# ADR 007: Upload and export files behind a storage interface on a shared volume

- Status: Accepted
- Date: 2026-10-11

## Context

Uploaded CSVs must be read by the API (validation, preview, mapping dry runs) and by a
Celery worker (processing). Report exports are written by a worker and downloaded
through the API. Both processes need the same files, and a cloud object store would be
a new service the project does not otherwise need.

## Decision

- A small `Storage` protocol (`app/storage.py`) with `save`, `write_bytes`, `open`,
  `delete`, and `exists`. The only implementation is `LocalStorage(root)`.
- In Compose the root (`STORAGE_DIR=/app/data/storage`) is the named volume
  `user-storage`, mounted into both `backend` and `worker`.
- Two areas: `uploads/` and `exports/`. Files are stored under a random UUID name with a
  fixed suffix. The user's filename is sanitized and kept only for display; it never
  becomes part of a path. `_path()` rejects any key that is not `area/name` with a known
  area, so traversal (`../`) is impossible even if a key were tampered with.
- Uploads stream to a `.part` file and are rejected with 413 as soon as they pass
  **25 MB** (also checked up front from `Content-Length`). The file is renamed into
  place only after the size check.
- The uploaded CSV is **deleted after successful processing** (`storage_key` becomes
  null). Remapping then requires uploading the file again, which the UI explains. A
  failed or unprocessed upload keeps its file so the user can fix the mapping.
- Any failure during upload creation deletes the stored file.

## Consequences

- Swapping in S3 later means one new class; callers depend only on the protocol.
- One host (or a shared filesystem) is required for API and workers; fine for Compose,
  documented as a limit for horizontal scaling.
- Keeping raw files only until processing limits how much user data sits on disk.

## Alternatives considered

- **Store files in PostgreSQL (`bytea`).** Simple, but bloats the database and backups
  with data that is deleted minutes later.
- **Object storage (S3/MinIO) now.** More moving parts than the milestone needs.
