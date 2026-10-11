# ADR 009: argon2id passwords and JWT sessions in an httpOnly cookie

- Status: Accepted
- Date: 2026-10-11

## Context

Uploads, saved reports, and exports are private, so M3 needs accounts. The app is a
single-origin SPA served next to its API, and it should not hold tokens in JavaScript.

## Decision

- **Passwords** are hashed with argon2id (`argon2-cffi` defaults: t=3, m=64 MiB, p=4).
  Minimum length 10, maximum 128. Hashes are rehashed on login if parameters change.
  Verification of an unknown email still runs one argon2 verify, so response time does
  not reveal which emails exist.
- **Sessions** are HS256 JWTs (PyJWT) with `sub`, `iat`, `exp` (12h), and a `ver`
  claim matching `users.token_version`. They are set in the `piq_session` cookie:
  `HttpOnly`, `SameSite=Lax`, `Path=/`, and `Secure` when `COOKIE_SECURE=true`.
  `POST /auth/logout-all` increments `token_version`, which revokes every session.
- **CSRF**: every unsafe request (POST, PUT, PATCH, DELETE) must carry
  `X-PlaybookIQ-CSRF: 1`, or it is rejected with 403 `csrf_failed`. A cross-site form
  cannot add a custom header, and a cross-site `fetch` with one triggers a CORS
  preflight that only the configured origins (`CORS_ORIGINS`) pass. `SameSite=Lax` is a second layer.
- With `ENVIRONMENT=production`, the default development `JWT_SECRET` or any secret
  shorter than 32 characters is a startup error.

## Consequences

- No token storage in the browser; XSS cannot read the session.
- Stateless verification on every request, plus one indexed lookup of the user (needed
  anyway for `is_admin` and `token_version`).
- Revoking a single session is not possible, only all of a user's sessions. Acceptable
  at this scale.

## Alternatives considered

- **Server-side session table.** Easy per-session revocation, but one more table and
  lookup for no current need.
- **Bearer tokens in `localStorage`.** Exposed to XSS.
- **An external identity provider.** `external_auth_id` is reserved for it later.
