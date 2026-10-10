from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mini_jira.auth.tokens import create_access_token
from mini_jira.main import app
from mini_jira.users.schemas import (
    UserCredentials,
    UserProfileUpdate,
    UserRegister,
)
from tests.factories import registration_data

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "changes",
    [
        {"username": "x"},
        {"username": "invalid_name"},
        {"username": "u" * 33},
        {"email": "invalid-email"},
        {"password": "short"},
        {"password": "1234567"},
        {"password": ""},
    ],
)
def test_registration_validators_reject_invalid_input(
    changes: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        UserRegister(**(registration_data() | changes))


def test_profile_normalization_and_optional_fields() -> None:
    user = UserRegister(**(registration_data() | {"username": "Mixed-Case"}))
    assert user.username == "mixed-case"
    update = UserProfileUpdate(
        username="Changed-Name", email="new@EXAMPLE.ORG"
    )
    assert update.username == "changed-name"
    assert str(update.email) == "new@example.org"
    optional = UserProfileUpdate(username=None, email=None)
    assert optional.username is None and optional.email is None


@pytest.mark.parametrize("username", ["-leading", "trailing-", "bad_name"])
def test_profile_rejects_invalid_username(username: str) -> None:
    with pytest.raises(ValidationError) as raised:
        UserProfileUpdate(username=username)
    error = raised.value.errors(include_input=False)[0]
    assert error["type"] == "username_invalid"
    assert not error["msg"].startswith("Value error,")
    assert "ctx" not in error
    assert username not in error["msg"]


@pytest.mark.parametrize(
    "changes,error_type,message",
    [
        (
            {"username": "invalid_name"},
            "username_invalid",
            "Username must contain only Latin letters, digits, and hyphens"
            " (hyphen cannot be at start or end)",
        ),
        (
            {"password": "private"},
            "string_too_short",
            "String should have at least 8 characters",
        ),
        (
            {"username": "u" * 33},
            "string_too_long",
            "String should have at most 32 characters",
        ),
        (
            {"email": "private-invalid-email"},
            "email_invalid",
            "Email address is invalid",
        ),
    ],
)
def test_registration_custom_errors_are_safe(
    changes: dict[str, str], error_type: str, message: str
) -> None:
    payload = registration_data() | changes
    response = TestClient(app).post("/auth/register", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "type": error_type,
            "loc": ["body", next(iter(changes))],
            "msg": message,
        }
    ]
    assert all(value not in response.text for value in payload.values())


@pytest.mark.parametrize("model", [UserRegister, UserProfileUpdate])
def test_email_schemas_reject_invalid_addresses(
    model: type[UserRegister] | type[UserProfileUpdate],
) -> None:
    payload = registration_data() | {"email": "private-user@"}
    with pytest.raises(ValidationError) as raised:
        model(**payload)
    error = raised.value.errors(include_input=False)[0]
    assert error["type"] == "value_error"


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/auth/register", {"password": "private-short"}),
        (
            "/auth/register",
            registration_data() | {"email": "private-invalid-email"},
        ),
        ("/auth/login", {"login": {"private": "value"}, "password": 7}),
        ("/users/me", {"username": "private_invalid"}),
        ("/users/me", {"username": "u" * 33}),
    ],
)
def test_builtin_and_profile_validation_responses_are_sanitized(
    path: str, payload: dict[str, object]
) -> None:
    with TestClient(app) as client:
        if path == "/users/me":
            token = create_access_token(uuid4())
            response = client.patch(
                path,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert token not in response.text
        else:
            response = client.post(path, json=payload)
    assert response.status_code == 422
    assert all(
        set(error) == {"type", "loc", "msg"}
        for error in response.json()["detail"]
    )
    assert "private" not in response.text
    assert registration_data()["password"] not in response.text


@pytest.mark.parametrize(
    "password", ["lowercase123", "PasswordOnly", "abcdefgh", "12345678"]
)
def test_credentials_and_registration_accept_current_password_policy(
    password: str,
) -> None:
    credentials = UserCredentials(login="Mixed-Case", password=password)
    assert credentials.model_dump() == {
        "login": "Mixed-Case",
        "password": password,
    }
    assert (
        UserRegister(**(registration_data() | {"password": password})).password
        == password
    )


@pytest.mark.parametrize("password", ["", "short", "1234567"])
def test_credentials_reject_short_passwords(password: str) -> None:
    with pytest.raises(ValidationError):
        UserCredentials(login="test-user", password=password)


@pytest.mark.parametrize("model", [UserRegister, UserProfileUpdate])
def test_username_length_boundary(
    model: type[UserRegister] | type[UserProfileUpdate],
) -> None:
    assert (
        model(**(registration_data() | {"username": "U" * 32})).username
        == "u" * 32
    )
    with pytest.raises(ValidationError) as raised:
        model(**(registration_data() | {"username": "u" * 33}))
    assert (
        raised.value.errors(include_input=False)[0]["type"]
        == "string_too_long"
    )
