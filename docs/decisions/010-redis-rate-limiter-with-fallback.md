# ADR 010: Redis fixed-window rate limiter with an in-process fallback for auth

- Status: Accepted
- Date: 2026-10-11

## Context

Login and register need brute-force protection. Uploads, report generation, and exports
start background work and need abuse limits. Redis is already present, but it is
optional elsewhere in the app ([ADR 005](005-celery-job-model.md)): the API keeps
working when it is down.

## Decision

- A fixed-window counter per `(rule, identity)`: `INCR piq:rl:{rule}:{identity}:{window}`
  with an expiry on first use. One round trip per request.
- Rules (`app/auth/ratelimit.py`):

  | Rule | Limit | Identity |
  | --- | --- | --- |
  | `login_ip` | 30 / minute | client IP |
  | `login_email` | 10 / 15 minutes | normalized email |
  | `register_ip` | 20 / hour | client IP |
  | `upload` | 30 / hour | user |
  | `report` | 60 / hour | user |
  | `export` | 60 / hour | user |

- Over the limit returns 429 `rate_limited` with `Retry-After`.
- **When Redis is unavailable**, the `strict` rules (login, register) fall back to a
  per-process in-memory counter, so brute-force protection never disappears. The other
  rules fail open, so a Redis outage does not take uploads and reports down.
- The client IP is the socket peer. `X-Forwarded-For` is not trusted, because any client
  can set it.

## Consequences

- Fixed windows allow up to 2x the limit across a window boundary. Acceptable for abuse
  protection; this is not billing.
- The in-process fallback is per worker process, so the effective limit during an
  outage is limit x processes. Still bounded.
- Behind a reverse proxy every client shares the proxy's IP for the per-IP rules. A
  deployment behind a proxy needs trusted-proxy handling first (not built in M3).

## Alternatives considered

- **Sliding-window log or token bucket in Lua.** More precise, more code, no practical
  benefit here.
- **A limiter library (slowapi).** Another dependency, and it does not express "strict
  rules fall back, others fail open".
