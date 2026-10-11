"""Registration, login, sessions, CSRF, and rate limiting against PostgreSQL + Redis."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.tokens import issue_token
from app.models import ApiUsage, User
from tests.integration.conftest import PASSWORD, api_client, create_user, sign_in

pytestmark = pytest.mark.integration

ME = "/api/v1/auth/me"


@pytest.fixture
async def client(db_session: Session) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(db_session) as c:
        yield c


async def test_register_sets_session_cookie(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "  Coach@Example.com ", "password": PASSWORD}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "coach@example.com"
    assert body["is_admin"] is False
    assert "password" not in str(body)
    cookie = resp.headers["set-cookie"].lower()
    assert "piq_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert (await client.get(ME)).json()["email"] == "coach@example.com"


async def test_register_validation_and_duplicates(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    create_user(db_session, "taken@example.com")
    dup = await client.post(
        "/api/v1/auth/register", json={"email": "TAKEN@example.com", "password": PASSWORD}
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "email_taken"
    short = await client.post(
        "/api/v1/auth/register", json={"email": "new@example.com", "password": "short"}
    )
    assert short.status_code == 422
    bad_email = await client.post(
        "/api/v1/auth/register", json={"email": "not-an-email", "password": PASSWORD}
    )
    assert bad_email.status_code == 422


async def test_password_is_hashed_with_argon2id(db_session: Session) -> None:
    user = create_user(db_session, "hash@example.com")
    assert user.password_hash is not None
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


async def test_login_failures_do_not_reveal_which_part_was_wrong(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    create_user(db_session, "real@example.com")
    wrong_pw = await client.post(
        "/api/v1/auth/login", json={"email": "real@example.com", "password": "nope-nope-nope"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": PASSWORD}
    )
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert (await client.get(ME)).status_code == 401


async def test_logout_clears_cookie(client: httpx.AsyncClient, db_session: Session) -> None:
    create_user(db_session, "out@example.com")
    await sign_in(client, "out@example.com")
    assert (await client.get(ME)).status_code == 200
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get(ME)).status_code == 401


async def test_logout_all_revokes_existing_tokens(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    user = create_user(db_session, "multi@example.com")
    await sign_in(client, "multi@example.com")
    other_device = client.cookies.get("piq_session")
    assert (await client.post("/api/v1/auth/logout-all")).status_code == 204
    client.cookies.set("piq_session", other_device or "")
    assert (await client.get(ME)).status_code == 401
    db_session.refresh(user)
    assert user.token_version == 1


async def test_forged_and_expired_tokens_are_rejected(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    from datetime import UTC, datetime, timedelta

    import jwt

    user = create_user(db_session, "victim@example.com")
    forged = jwt.encode(
        {"sub": str(user.id), "ver": 0, "iat": 0, "exp": 9999999999}, "x" * 40, algorithm="HS256"
    )
    client.cookies.set("piq_session", forged)
    assert (await client.get(ME)).status_code == 401
    expired = issue_token(user.id, 0, now=datetime.now(UTC) - timedelta(days=2))
    client.cookies.set("piq_session", expired)
    assert (await client.get(ME)).status_code == 401
    client.cookies.set("piq_session", issue_token(user.id, 0))
    assert (await client.get(ME)).status_code == 200


async def test_unsafe_requests_require_csrf_header(db_session: Session) -> None:
    create_user(db_session, "csrf@example.com")
    async with api_client(db_session) as c:
        await sign_in(c, "csrf@example.com")
        resp = await c.post("/api/v1/auth/logout", headers={"X-PlaybookIQ-CSRF": ""})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "csrf_failed"
        # Reads are unaffected.
        assert (await c.get(ME, headers={"X-PlaybookIQ-CSRF": ""})).status_code == 200


async def test_login_is_rate_limited_per_email(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    create_user(db_session, "brute@example.com")
    body = {"email": "brute@example.com", "password": "wrong-password-x"}
    statuses = [(await client.post("/api/v1/auth/login", json=body)).status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    limited = await client.post("/api/v1/auth/login", json={**body, "password": PASSWORD})
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0


async def test_private_requests_are_recorded_in_api_usage(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    user = create_user(db_session, "usage@example.com")
    await sign_in(client, "usage@example.com")
    await client.get(ME)
    # /auth/me is not tracked; job cancellation (a private action) is.
    await client.post("/api/v1/jobs/00000000-0000-0000-0000-000000000000/cancel")
    rows = db_session.scalars(select(ApiUsage).where(ApiUsage.user_id == user.id)).all()
    assert [(r.method, r.endpoint) for r in rows] == [("POST", "/api/v1/jobs/{job_id}/cancel")]
    assert db_session.scalar(select(func.count()).select_from(User)) == 1
