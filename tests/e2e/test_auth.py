from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from unittest.mock import patch

import httpx2 as httpx
import pytest
from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.service import validate_access_token
from mini_jira.auth.tokens import hash_refresh_token
from mini_jira.config import settings
from mini_jira.database.models import RefreshToken, User
from tests.factories import (
    PASSWORD,
    RegisteredUser,
    registration_data,
    signed_token,
)

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]


async def test_registration_persists_and_sets_safe_cookie(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    data = registration_data()
    response = await client.post("/auth/register", json=data)
    assert response.status_code == 201
    assert response.json()["token_type"] == "bearer"
    user_id = validate_access_token(response.json()["access_token"])
    user = await db_session.get(User, user_id)
    assert user is not None
    assert user.username == data["username"]
    assert user.email == data["email"]
    assert user.password_hash != PASSWORD
    assert PasswordHash.recommended().verify(PASSWORD, user.password_hash)
    cookie = SimpleCookie(response.headers["set-cookie"])["refresh_token"]
    assert cookie["httponly"]
    assert bool(cookie["secure"]) == settings.refresh_cookie_secure
    assert cookie["samesite"] == settings.refresh_cookie_samesite
    assert cookie["path"] == "/auth"
    assert cookie["domain"] == (settings.refresh_cookie_domain or "")
    token = await db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(cookie.value)
        )
    )
    assert token is not None
    assert token.user_id == user_id
    assert not token.revoked
    assert token.token_hash != cookie.value


@pytest.mark.parametrize("field", ["username", "email"])
async def test_registration_conflict_is_atomic(
    field: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    await register(1)
    payload = registration_data(2)
    payload[field] = registration_data(1)[field]
    client.cookies.clear()
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 409
    assert "access_token" not in response.json()
    assert "set-cookie" not in response.headers
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1
    assert (
        await db_session.scalar(select(func.count()).select_from(RefreshToken))
        == 1
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"username": "x"},
        {"username": "invalid_name"},
        {"email": "not-an-email"},
        {"password": "short"},
        {"password": "1234567"},
        {"password": ""},
    ],
)
async def test_registration_validation_no_partial_data(
    changes: dict[str, str],
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = registration_data() | changes
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 422
    assert "set-cookie" not in response.headers
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0
    assert (
        await db_session.scalar(select(func.count()).select_from(RefreshToken))
        == 0
    )


@pytest.mark.parametrize("login_field", ["username", "email"])
async def test_login_revokes_previous_cookie(
    login_field: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    user = await register(1)
    login = user.username if login_field == "username" else user.email
    response = await client.post(
        "/auth/login", json={"login": login, "password": PASSWORD}
    )
    assert response.status_code == 200
    assert validate_access_token(response.json()["access_token"]) == user.id
    assert client.cookies.get("refresh_token") != user.refresh
    old = await db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(user.refresh)
        )
    )
    assert old is not None and old.revoked
    client.cookies.clear()
    denied = await client.post(
        "/auth/refresh", headers={"Cookie": f"refresh_token={user.refresh}"}
    )
    assert denied.status_code == 401


@pytest.mark.parametrize(
    "login,password",
    [
        ("test-user-1", "wrong-password"),
        ("unknown-user", PASSWORD),
    ],
)
async def test_failed_login_issues_no_tokens(
    login: str,
    password: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    await register(1)
    client.cookies.clear()
    response = await client.post(
        "/auth/login", json={"login": login, "password": password}
    )
    assert response.status_code == 401
    assert "access_token" not in response.json()
    assert "set-cookie" not in response.headers
    assert (
        await db_session.scalar(select(func.count()).select_from(RefreshToken))
        == 1
    )


@pytest.mark.parametrize(
    "payload", [{}, {"login": "user"}, {"login": 7, "password": 8}]
)
async def test_login_validation(
    payload: dict[str, object], client: httpx.AsyncClient
) -> None:
    response = await client.post("/auth/login", json=payload)
    assert response.status_code == 422
    assert "set-cookie" not in response.headers


async def test_refresh_rotation_and_replay(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    user = await register(1)
    response = await client.post("/auth/refresh")
    assert response.status_code == 200
    assert validate_access_token(response.json()["access_token"]) == user.id
    new = client.cookies.get("refresh_token")
    assert new and new != user.refresh
    old = await db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(user.refresh)
        )
    )
    assert old is not None and old.revoked
    client.cookies.clear()
    assert (
        await client.post(
            "/auth/refresh",
            headers={"Cookie": f"refresh_token={user.refresh}"},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/auth/refresh", headers={"Cookie": f"refresh_token={new}"}
        )
    ).status_code == 200


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "damaged",
        "expired",
        "revoked",
        "access",
        "unpersisted",
        "database_expired",
    ],
)
async def test_invalid_refresh_is_rejected(
    kind: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    user = await register(1)
    token = user.refresh
    record = await db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(token)
        )
    )
    assert record is not None
    if kind == "expired":
        token = signed_token(user.id, expired=True)
    elif kind == "unpersisted":
        token = signed_token(user.id)
    elif kind == "damaged":
        token = "broken.jwt.signature"
    elif kind == "access":
        token = user.access
    elif kind == "revoked":
        record.revoked = True
        await db_session.commit()
    elif kind == "database_expired":
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db_session.commit()
    client.cookies.clear()
    headers = {} if kind == "missing" else {"Cookie": f"refresh_token={token}"}
    response = await client.post("/auth/refresh", headers=headers)
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert "access_token" not in response.json()


async def test_logout_revokes_and_clears_cookie(
    client: httpx.AsyncClient,
    register: Callable[[int], Awaitable[RegisteredUser]],
    db_session: AsyncSession,
) -> None:
    user = await register(1)
    response = await client.post("/auth/logout")
    assert response.status_code == 200
    assert response.json() is None
    cookie = SimpleCookie(response.headers["set-cookie"])["refresh_token"]
    assert cookie["max-age"] == "0"
    assert cookie["path"] == "/auth"
    assert not client.cookies.get("refresh_token")
    old = await db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(user.refresh)
        )
    )
    assert old is not None and old.revoked
    assert (
        await client.post(
            "/auth/refresh",
            headers={"Cookie": f"refresh_token={user.refresh}"},
        )
    ).status_code == 401
    assert (await client.post("/auth/logout")).status_code == 200


async def test_registration_token_failure_rolls_back_new_user(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    existing = await register(1)
    client.cookies.clear()
    with patch(
        "mini_jira.auth.service.create_refresh_token",
        return_value=existing.refresh,
    ):
        response = await client.post(
            "/auth/register", json=registration_data(2)
        )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "set-cookie" not in response.headers
    assert existing.refresh not in response.text
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1
    assert (
        await db_session.scalar(select(func.count()).select_from(RefreshToken))
        == 1
    )


async def test_failed_rotation_preserves_previous_refresh(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    first = await register(1)
    second = await register(2)
    with patch(
        "mini_jira.auth.service.create_refresh_token",
        return_value=first.refresh,
    ):
        failed = await client.post("/auth/refresh")
    assert failed.status_code == 500
    assert failed.json() == {"detail": "Internal server error"}
    assert "set-cookie" not in failed.headers
    old = await db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(second.refresh)
        )
    )
    assert old is not None and not old.revoked
    assert (await client.post("/auth/refresh")).status_code == 200
