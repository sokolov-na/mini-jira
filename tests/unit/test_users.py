import pytest
from pydantic import ValidationError

from mini_jira.users.schemas import UserRegister, UserUpdate
from tests.factories import registration_data

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "changes",
    [
        {"username": "x"},
        {"username": "invalid_name"},
        {"email": "invalid-email"},
        {"password": "short"},
        {"password": "lowercase123"},
        {"password": "PasswordOnly"},
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
    update = UserUpdate(username="Changed-Name", email="new@EXAMPLE.ORG")
    assert update.username == "changed-name"
    assert str(update.email) == "new@example.org"
    optional = UserUpdate(username=None, email=None)
    assert optional.username is None and optional.email is None


@pytest.mark.parametrize("username", ["-leading", "trailing-", "bad_name"])
def test_profile_rejects_invalid_username(username: str) -> None:
    with pytest.raises(ValidationError):
        UserUpdate(username=username)
