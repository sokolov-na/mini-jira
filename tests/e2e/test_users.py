from collections.abc import Awaitable, Callable

import httpx2 as httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.database.models import RefreshToken, User
from tests.factories import RegisteredUser, registration_data, signed_token

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]


async def test_username_length_limit_registration_login_and_update(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    data = registration_data() | {"username": "u" * 32}
    rejected = await client.post(
        "/auth/register", json=data | {"username": "u" * 33}
    )
    assert rejected.status_code == 422
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0
    registered = await client.post("/auth/register", json=data)
    assert registered.status_code == 201
    login = await client.post(
        "/auth/login",
        json={"login": data["username"], "password": data["password"]},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    updated = await client.patch(
        "/users/me", headers=headers, json={"username": "v" * 32}
    )
    assert updated.status_code == 200
    rejected_update = await client.patch(
        "/users/me", headers=headers, json={"username": "v" * 33}
    )
    assert rejected_update.status_code == 422
    assert rejected_update.json()["detail"] == [
        {
            "type": "string_too_long",
            "loc": ["body", "username"],
            "msg": "String should have at most 32 characters",
        }
    ]
    assert "v" * 33 not in rejected_update.text
    db_session.expire_all()
    user = await db_session.scalar(select(User))
    assert user is not None and user.username == "v" * 32


async def test_profile_is_own_and_persisted_update(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    first = await register(1)
    second = await register(2)
    headers = {"Authorization": f"Bearer {first.access}"}
    response = await client.get("/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "id": str(first.id),
        "username": first.username,
        "email": first.email,
    }
    updated = await client.patch(
        "/users/me",
        headers=headers,
        json={
            "id": str(second.id),
            "username": "changed-user",
            "email": "changed@example.org",
            "password": "ignored-password",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == str(first.id)
    one = await db_session.get(User, first.id)
    two = await db_session.get(User, second.id)
    assert one and two
    assert one.username == "changed-user"
    assert one.email == "changed@example.org"
    assert two.username == second.username
    assert two.email == second.email
    assert (
        await client.get(f"/users/{second.id}", headers=headers)
    ).status_code == 404


@pytest.mark.parametrize("field", ["username", "email"])
async def test_update_conflict_rolls_back(
    field: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    first = await register(1)
    second = await register(2)
    changes = {
        "username": "changed-before-conflict",
        "email": "changed@example.org",
    }
    changes[field] = second.username if field == "username" else second.email
    response = await client.patch(
        "/users/me",
        headers={
            "Authorization": f"Bearer {first.access}",
        },
        json=changes,
    )
    assert response.status_code == 409
    db_session.expire_all()
    user = await db_session.get(User, first.id)
    assert (
        user and user.username == first.username and user.email == first.email
    )
    assert await db_session.scalar(select(func.count()).select_from(User)) == 2


@pytest.mark.parametrize(
    "changes", [{"username": "bad_name"}, {"email": "bad-email"}]
)
async def test_update_validation(
    changes: dict[str, str],
    client: httpx.AsyncClient,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    user = await register(1)
    response = await client.patch(
        "/users/me",
        headers={
            "Authorization": f"Bearer {user.access}",
        },
        json=changes,
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "kind", ["missing", "invalid", "refresh", "forged", "expired"]
)
async def test_profile_rejects_invalid_access(
    kind: str,
    client: httpx.AsyncClient,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    user = await register(1)
    token = "broken.jwt.signature"
    if kind == "refresh":
        token = user.refresh
    elif kind == "forged":
        token = signed_token(
            user.id, "access", key="wrong-test-signing-key-long-enough"
        )
    elif kind == "expired":
        token = signed_token(user.id, "access", expired=True)
    headers = {} if kind == "missing" else {"Authorization": f"Bearer {token}"}
    response = await client.get("/users/me", headers=headers)
    assert response.status_code == 401
    assert "password" not in response.text
    assert "Traceback" not in response.text


async def test_delete_cascades_and_tokens_no_longer_access_profile(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    user = await register(1)
    headers = {"Authorization": f"Bearer {user.access}"}
    response = await client.delete("/users/me", headers=headers)
    assert response.status_code == 204
    assert response.content == b""
    assert await db_session.get(User, user.id) is None
    assert (
        await db_session.scalar(select(func.count()).select_from(RefreshToken))
        == 0
    )
    assert (await client.get("/users/me", headers=headers)).status_code == 404
    assert (
        await client.patch(
            "/users/me", headers=headers, json={"username": "after-delete"}
        )
    ).status_code == 404
    assert (
        await client.delete("/users/me", headers=headers)
    ).status_code == 404
    assert (await client.post("/auth/refresh")).status_code == 401
