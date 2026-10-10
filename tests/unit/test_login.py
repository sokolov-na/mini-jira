from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import dns.resolver
import pytest
from pwdlib import PasswordHash

from mini_jira.exceptions import InvalidCredentials
from mini_jira.users.models import User
from mini_jira.users.repository.protocol import UserRepository
from mini_jira.users.schemas import UserCredentials
from mini_jira.users.use_cases import LoginUserUseCase

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "login,email",
    [
        ("  User@EXAMPLE.ORG  ", "User@example.org"),
        ("Alice <User@EXAMPLE.ORG>", "User@example.org"),
        ("иван@ПРИМЕР.РФ", "иван@пример.рф"),
        ("user@xn--e1afmkfd.xn--p1ai", "user@пример.рф"),
        ("e\u0301@EXAMPLE.ORG", "é@example.org"),
    ],
)
async def test_login_normalizes_email_without_dns(
    login: str, email: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver = Mock(spec=dns.resolver.Resolver)
    resolver.resolve.side_effect = AssertionError("Unexpected DNS request")
    monkeypatch.setattr(dns.resolver, "get_default_resolver", lambda: resolver)
    user = User(
        id=uuid4(),
        username="test-user",
        email=email,
        password_hash=PasswordHash.recommended().hash("password"),
    )
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = user
    result = await LoginUserUseCase(cast(UserRepository, repository)).execute(
        UserCredentials(login=login, password="password")
    )
    assert result == user.id
    repository.get_by_email.assert_awaited_once_with(email, for_update=True)
    repository.get_by_username.assert_not_awaited()
    resolver.resolve.assert_not_called()


@pytest.mark.parametrize(
    "login", ["test-user", "broken@", "user..name@host.org"]
)
async def test_non_email_login_keeps_username_fallback(login: str) -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_username.return_value = None
    with pytest.raises(InvalidCredentials):
        await LoginUserUseCase(cast(UserRepository, repository)).execute(
            UserCredentials(login=login, password="password")
        )
    repository.get_by_username.assert_awaited_once_with(login, for_update=True)
    repository.get_by_email.assert_not_awaited()


async def test_unknown_valid_email_does_not_fall_back_to_username() -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = None
    with pytest.raises(InvalidCredentials):
        await LoginUserUseCase(cast(UserRepository, repository)).execute(
            UserCredentials(login="missing@example.org", password="password")
        )
    repository.get_by_email.assert_awaited_once_with(
        "missing@example.org", for_update=True
    )
    repository.get_by_username.assert_not_awaited()
