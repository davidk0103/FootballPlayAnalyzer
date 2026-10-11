"""Password hashing with argon2id (memory-hard, OWASP-recommended parameters)."""

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


@lru_cache
def _hasher() -> PasswordHasher:
    # argon2-cffi defaults: argon2id, t=3, m=64 MiB, p=4 (RFC 9106 "second recommended").
    return PasswordHasher()


@lru_cache
def _dummy_hash() -> str:
    return _hasher().hash("dummy-password-for-timing-equalization")


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-work verification: unknown users still pay for one argon2 verify,
    so response time does not reveal whether an email is registered."""
    try:
        return _hasher().verify(password_hash or _dummy_hash(), password) and bool(password_hash)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher().check_needs_rehash(password_hash)
