from typing import Annotated
from unittest.mock import Mock, patch

import dns.resolver
import pytest
from email_validator import validate_email
from fastapi.testclient import TestClient
from pydantic import (
    EmailStr,
    TypeAdapter,
    ValidationError,
    ValidatorFunctionWrapHandler,
    WrapValidator,
)
from pydantic_core import PydanticCustomError

from mini_jira.main import app
from mini_jira.users import schemas
from tests.factories import registration_data

pytestmark = pytest.mark.unit

EMAIL_CASES = [
    ("ordinary", "user@example.org"),
    ("domain_case", "user@EXAMPLE.ORG"),
    ("local_case", "User.Name@example.org"),
    ("reserved_mailbox", "Postmaster@EXAMPLE.ORG"),
    ("spaces", "  User@EXAMPLE.ORG  "),
    ("display_name", "Alice <User@EXAMPLE.ORG>"),
    ("unicode_local", "иван@example.org"),
    ("unicode_domain", "user@пример.рф"),
    ("punycode", "user@xn--e1afmkfd.xn--p1ai"),
    ("nfc", "e\u0301@example.org"),
    (
        "fullwidth_domain",
        "user@\uff25\uff38\uff21\uff2d\uff30\uff2c\uff25.org",
    ),
    ("tag", "user+tag@example.org"),
    ("apostrophe", "o'hara@example.org"),
    ("quoted", '"user name"@example.org'),
    ("empty", ""),
    ("missing_at", "private-address"),
    ("missing_domain", "private-address@"),
    ("missing_local", "@example.org"),
    ("double_local_dot", "user..name@example.org"),
    ("leading_local_dot", ".user@example.org"),
    ("trailing_local_dot", "user.@example.org"),
    ("double_domain_dot", "user@example..org"),
    ("trailing_domain_dot", "user@example.org."),
    ("forbidden", "user,private@example.org"),
    ("domain_underscore", "user@private_domain.org"),
    ("ip_literal", "user@[127.0.0.1]"),
    ("localhost", "user@localhost"),
    ("reserved_test", "user@example.test"),
    ("long_local", "x" * 65 + "@example.org"),
    ("control", "user\nprivate@example.org"),
    ("none", None),
    ("number", 123),
]


@pytest.mark.parametrize(
    "case,value", EMAIL_CASES, ids=[case for case, _ in EMAIL_CASES]
)
def test_email_variants_agree_with_deliverable_domain(
    case: str, value: object
) -> None:
    builtin = TypeAdapter[str](EmailStr)
    try:
        normalized = builtin.validate_python(value)
    except ValidationError as builtin_error:
        with pytest.raises(ValidationError) as registration_error:
            schemas.UserRegister.model_validate(
                registration_data() | {"email": value}
            )
        actual = registration_error.value.errors(include_input=False)[0]
        expected = builtin_error.errors(include_input=False)[0]
        assert actual["type"] == expected["type"]
        assert actual["msg"] == expected["msg"]
    else:
        assert (
            schemas.UserRegister.model_validate(
                registration_data() | {"email": value}
            ).email
            == normalized
        )
        assert (
            schemas.UserProfileUpdate.model_validate({"email": value}).email
            == normalized
        )
        assert isinstance(value, str)
        assert schemas.normalize_email(value) == normalized


@pytest.mark.parametrize(
    "value,normalized",
    [
        ("  User@EXAMPLE.ORG  ", "User@example.org"),
        ("user@xn--e1afmkfd.xn--p1ai", "user@пример.рф"),
        ("e\u0301@example.org", "é@example.org"),
        ("Alice <User@EXAMPLE.ORG>", "User@example.org"),
    ],
)
def test_builtin_email_already_normalizes(value: str, normalized: str) -> None:
    assert TypeAdapter(EmailStr).validate_python(value) == normalized


@pytest.mark.parametrize(
    "value", ["  User@EXAMPLE.ORG  ", "Alice <User@EXAMPLE.ORG>"]
)
def test_registration_and_login_share_email_normalization(
    value: str,
) -> None:
    assert (
        schemas.UserRegister(**(registration_data() | {"email": value})).email
        == schemas.normalize_email(value)
        == "User@example.org"
    )


def test_email_normalization_does_not_check_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = Mock(spec=dns.resolver.Resolver)
    resolver.resolve.side_effect = dns.resolver.NXDOMAIN
    monkeypatch.setattr(dns.resolver, "get_default_resolver", lambda: resolver)
    value = "private-user@private-domain.org"
    assert TypeAdapter(EmailStr).validate_python(value) == value
    resolver.resolve.assert_not_called()
    assert schemas.normalize_email(value) == value
    assert (
        schemas.UserRegister(**(registration_data() | {"email": value})).email
        == value
    )
    resolver.resolve.assert_not_called()


@pytest.mark.parametrize(
    "value",
    ["private-address", "private-user..name@example.org", "private-user@"],
)
def test_email_response_uses_safe_custom_code(value: str) -> None:
    response = TestClient(app).post(
        "/auth/register", json=registration_data() | {"email": value}
    )
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert set(error) == {"type", "loc", "msg"}
    assert error["type"] == "email_invalid"
    assert error["msg"] == "Email address is invalid"
    assert value not in response.text


@pytest.mark.parametrize(
    "email",
    [
        "private-user,secret@example.org",
        "private-user..secret@example.org",
        None,
        ["private-address"],
        {"private-key": "private-value"},
    ],
)
def test_email_errors_do_not_echo_input_or_context(email: object) -> None:
    response = TestClient(app).post(
        "/auth/register", json=registration_data() | {"email": email}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "type": "email_invalid",
            "loc": ["body", "email"],
            "msg": "Email address is invalid",
        }
    ]
    assert "private" not in response.text
    assert registration_data()["password"] not in response.text


def test_profile_email_validation_is_safe_without_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = Mock(spec=dns.resolver.Resolver)
    resolver.resolve.side_effect = dns.resolver.NXDOMAIN
    monkeypatch.setattr(dns.resolver, "get_default_resolver", lambda: resolver)
    from uuid import uuid4

    from mini_jira.auth.tokens import create_access_token

    value = "private-user@"
    token = create_access_token(uuid4())
    response = TestClient(app).patch(
        "/users/me",
        json={"email": value},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "type": "email_invalid",
            "loc": ["body", "email"],
            "msg": "Email address is invalid",
        }
    ]
    assert value not in response.text
    assert token not in response.text
    resolver.resolve.assert_not_called()


@pytest.mark.parametrize("value", ["User@EXAMPLE.ORG", "private-user@"])
def test_wrap_candidate_relabels_errors_without_revalidation(
    value: str,
) -> None:
    def rewrite_error(
        value: object, handler: ValidatorFunctionWrapHandler
    ) -> str:
        try:
            return str(handler(value))
        except ValidationError as exc:
            raise PydanticCustomError(
                "email_invalid", "Email address is invalid"
            ) from exc

    candidate = TypeAdapter[str](
        Annotated[EmailStr, WrapValidator(rewrite_error)]
    )
    with patch(
        "email_validator.validate_email", wraps=validate_email
    ) as validation:
        if value.endswith("@"):
            with pytest.raises(ValidationError) as raised:
                candidate.validate_python(value)
            error = raised.value.errors(include_input=False)[0]
            assert error["type"] == "email_invalid"
            assert error["msg"] == "Email address is invalid"
            assert "ctx" not in error
        else:
            assert candidate.validate_python(value) == "User@example.org"
        validation.assert_called_once()
        assert validation.call_args.kwargs["check_deliverability"] is False
