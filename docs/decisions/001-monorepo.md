# ADR 001: Monorepo

- Status: Accepted
- Date: 2026-10-10

## Context

PlaybookIQ has a Python backend and a TypeScript frontend that share an API
contract. The frontend's API types are generated from the backend's OpenAPI
schema, and CI checks that they do not drift.

## Decision

Keep `backend/`, `frontend/`, and `docs/` in one repository with one CI workflow
and one Docker Compose file.

## Consequences

- A contract change and its frontend update land in one commit, and the drift
  check can run in CI without cross-repo coordination.
- Each side keeps its own toolchain (uv for Python, npm for the frontend); there
  is no monorepo build tool.
- CI runs both pipelines on every push. Path filters can be added if it gets slow.
