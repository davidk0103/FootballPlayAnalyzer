"""Registration, login, and session resolution."""

import re
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.auth.tokens import decode_token
from app.models import User
from app.services.errors import ConflictError, InvalidRequestError, UnauthorizedError

# Deliberately loose: one "@", a dot in the domain, no whitespace. Deliverability is not
# checked (there is no email verification flow).
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise InvalidRequestError("Enter a valid email address")
    return value


def validate_password(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidRequestError(
            f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters"
        )


def register(session: Session, *, email: str, password: str, is_admin: bool = False) -> User:
    address = normalize_email(email)
    validate_password(password)
    user = User(
        email=address, password_hash=hash_password(password), is_admin=is_admin, token_version=0
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("email_taken", "An account with this email already exists") from exc
    return user


def authenticate(session: Session, *, email: str, password: str) -> User:
    """Return the user for valid credentials. Errors never reveal which part was wrong."""
    try:
        address = normalize_email(email)
    except InvalidRequestError:
        address = ""
    user = session.scalar(select(User).where(User.email == address)) if address else None
    if not verify_password(user.password_hash if user else None, password) or user is None:
        raise UnauthorizedError("Incorrect email or password", code="invalid_credentials")
    assert user.password_hash is not None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    session.commit()
    return user


def user_for_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    claims = decode_token(token)
    if claims is None:
        return None
    user = session.get(User, claims.user_id)
    if user is None or user.token_version != claims.version:
        return None
    return user


def revoke_all_sessions(session: Session, user: User) -> None:
    session.execute(
        update(User).where(User.id == user.id).values(token_version=User.token_version + 1)
    )
    session.commit()
    session.refresh(user)


def set_admin(session: Session, email: str, *, is_admin: bool) -> User:
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        raise InvalidRequestError(f"No user with email {email}")
    user.is_admin = is_admin
    session.commit()
    return user
