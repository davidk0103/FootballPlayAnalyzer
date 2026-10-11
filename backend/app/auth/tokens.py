"""Session tokens: HS256 JWTs carried in an httpOnly cookie.

Claims: ``sub`` (user id), ``ver`` (the user's token_version at issue time), ``iat``,
``exp``. A token is only accepted if ``ver`` still matches the database, which is how
logout-all and password changes revoke sessions without a server-side session store.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings

ALGORITHM = "HS256"


@dataclass(frozen=True)
class TokenClaims:
    user_id: int
    version: int


def issue_token(user_id: int, version: int, *, now: datetime | None = None) -> str:
    settings = get_settings()
    issued = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "ver": version,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(hours=settings.jwt_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenClaims | None:
    """Return the claims of a valid, unexpired token, or None for anything else."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "ver", "iat", "exp"]},
        )
        return TokenClaims(user_id=int(payload["sub"]), version=int(payload["ver"]))
    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None
