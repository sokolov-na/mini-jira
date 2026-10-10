from collections.abc import Awaitable, Callable
from unittest.mock import Mock

import dns.resolver
import httpx2 as httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.database.models import User
from tests.factories import RegisteredUser, registration_data

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]


@pytest.mark.parametrize(
    "email,normalized,login",
    [
        ("  User@EXAMPLE.ORG  ", "User@example.org", " User@EXAMPLE.ORG "),
        (
            "Alice <User@EXAMPLE.ORG>",
            "User@example.org",
            "Alice <User@EXAMPLE.ORG>",
        ),
        ("иван@ПРИМЕР.РФ", "иван@пример.рф", "иван@ПРИМЕР.РФ"),
        (
            "user@пример.рф",
            "user@пример.рф",
            "user@xn--e1afmkfd.xn--p1ai",
        ),
        ("e\u0301@EXAMPLE.ORG", "é@example.org", "e\u0301@EXAMPLE.ORG"),
    ],
)
async def test_registration_and_login_share_normalization(
    email: str,
    normalized: str,
    login: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = Mock(spec=dns.resolver.Resolver)
    resolver.resolve.side_effect = dns.resolver.NXDOMAIN
    monkeypatch.setattr(dns.resolver, "get_default_resolver", lambda: resolver)
    payload = registration_data() | {"email": email, "password": "password"}
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201
    stored = await db_session.scalar(select(User))
    assert stored is not None and stored.email == normalized
    for identifier in [login, stored.username]:
        response = await client.post(
            "/auth/login", json={"login": identifier, "password": "password"}
        )
        assert response.status_code == 200
    resolver.resolve.assert_not_called()


async def test_profile_update_normalizes_email_and_preserves_local_case(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    user = await register(1)
    response = await client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {user.access}"},
        json={"email": "Alice <Changed@EXAMPLE.ORG>"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "Changed@example.org"
    db_session.expire_all()
    stored = await db_session.get(User, user.id)
    assert stored and stored.email == "Changed@example.org"
    assert (
        await client.post(
            "/auth/login",
            json={"login": " Changed@EXAMPLE.ORG ", "password": user.password},
        )
    ).status_code == 200
    assert (
        await client.post(
            "/auth/login",
            json={"login": "changed@example.org", "password": user.password},
        )
    ).status_code == 401


@pytest.mark.parametrize("operation", ["register", "update"])
async def test_normalized_email_conflict_is_atomic(
    operation: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    first = await register(1)
    second = await register(2)
    duplicate = f"Alias <{first.email.replace('example.org', 'EXAMPLE.ORG')}>"
    if operation == "register":
        response = await client.post(
            "/auth/register", json=registration_data(3) | {"email": duplicate}
        )
    else:
        response = await client.patch(
            "/users/me",
            headers={"Authorization": f"Bearer {second.access}"},
            json={"email": duplicate},
        )
    assert response.status_code == 409
    assert response.json() == {"detail": "Email already exists"}
    assert await db_session.scalar(select(func.count()).select_from(User)) == 2
    db_session.expire_all()
    stored = await db_session.get(User, second.id)
    assert stored is not None and stored.email == second.email


@pytest.mark.parametrize("password", ["PasswordOnly", "12345678", "abcdefgh"])
async def test_registration_accepts_current_password_policy(
    password: str, client: httpx.AsyncClient
) -> None:
    payload = registration_data() | {"password": password}
    assert (
        await client.post("/auth/register", json=payload)
    ).status_code == 201
    assert (
        await client.post(
            "/auth/login",
            json={"login": payload["username"], "password": password},
        )
    ).status_code == 200


@pytest.mark.parametrize(
    "login", ["unknown-user", "broken@", "user..x@host.org"]
)
async def test_invalid_or_unknown_login_is_safe(
    login: str, client: httpx.AsyncClient
) -> None:
    response = await client.post(
        "/auth/login", json={"login": login, "password": "password"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid login or password"}
    assert "set-cookie" not in response.headers
