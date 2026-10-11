from datetime import UTC, datetime, timedelta

import pytest

from app.auth.passwords import hash_password, verify_password
from app.auth.ratelimit import RateLimiter, Rule
from app.auth.service import normalize_email
from app.auth.tokens import decode_token, issue_token
from app.config import DEV_JWT_SECRET, Settings
from app.services.errors import InvalidRequestError, RateLimitedError

DEAD_REDIS = "redis://127.0.0.1:1/0"


def test_password_hash_roundtrip() -> None:
    stored = hash_password("a long passphrase")
    assert stored.startswith("$argon2id$")
    assert verify_password(stored, "a long passphrase")
    assert not verify_password(stored, "a long passphrasE")
    assert not verify_password(None, "anything")
    assert not verify_password("not-a-hash", "anything")


def test_token_roundtrip_and_tampering() -> None:
    token = issue_token(42, 3)
    claims = decode_token(token)
    assert claims is not None
    assert (claims.user_id, claims.version) == (42, 3)
    head, body, sig = token.split(".")
    assert decode_token(f"{head}.{body}.{sig[::-1]}") is None
    assert decode_token("garbage") is None


def test_expired_token_is_rejected() -> None:
    old = issue_token(1, 0, now=datetime.now(UTC) - timedelta(hours=13))
    assert decode_token(old) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(" A@B.co ", "a@b.co"), ("first.last+tag@sub.example.org", "first.last+tag@sub.example.org")],
)
def test_normalize_email(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", ["", "no-at", "a@b", "a b@c.de", "a@@b.cd", "x" * 250 + "@b.cd"])
def test_normalize_email_rejects(raw: str) -> None:
    with pytest.raises(InvalidRequestError):
        normalize_email(raw)


def test_production_refuses_dev_secret() -> None:
    with pytest.raises(RuntimeError):
        Settings(environment="production", jwt_secret=DEV_JWT_SECRET).check_secrets()
    with pytest.raises(RuntimeError):
        Settings(environment="production", jwt_secret="short").check_secrets()
    Settings(environment="production", jwt_secret="z" * 48).check_secrets()
    Settings(environment="development").check_secrets()


def test_strict_rule_falls_back_to_local_counter_when_redis_is_down() -> None:
    limiter = RateLimiter(DEAD_REDIS, socket_timeout=0.05)
    rule = Rule("t", limit=2, window_seconds=60, strict=True)
    limiter.hit(rule, "ip", now=1000)
    limiter.hit(rule, "ip", now=1001)
    with pytest.raises(RateLimitedError) as exc:
        limiter.hit(rule, "ip", now=1002)
    assert exc.value.retry_after_seconds == 18  # window [960, 1020)
    # A new window resets the count.
    limiter.hit(rule, "ip", now=1080)


def test_lenient_rule_fails_open_when_redis_is_down() -> None:
    limiter = RateLimiter(DEAD_REDIS, socket_timeout=0.05)
    rule = Rule("t", limit=1, window_seconds=60)
    for _ in range(5):
        limiter.hit(rule, "user", now=1000)


def test_disabled_limiter_never_limits() -> None:
    limiter = RateLimiter(DEAD_REDIS, enabled=False)
    for _ in range(5):
        limiter.hit(Rule("t", limit=1, window_seconds=60, strict=True), "x")
