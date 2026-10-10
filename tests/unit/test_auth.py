from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from mini_jira.auth.service import validate_access_token
from mini_jira.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from mini_jira.config import settings
from mini_jira.exceptions import InvalidTokenError
from mini_jira.main import app
from tests.factories import signed_token

pytestmark = pytest.mark.unit


def test_token_types_signature_and_identifiers() -> None:
    user_id = uuid4()
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    assert validate_access_token(access) == user_id
    assert decode_token(refresh, "refresh")["sub"] == str(user_id)
    assert (
        decode_token(access, "access")["jti"]
        != decode_token(refresh, "refresh")["jti"]
    )
    with pytest.raises(InvalidTokenError):
        decode_token(access, "refresh")
    with pytest.raises(InvalidTokenError):
        decode_token(refresh, "access")


@pytest.mark.parametrize(
    "case",
    ["forged", "expired", "malformed", "invalid_subject", "missing_claim"],
)
def test_invalid_access_tokens(case: str) -> None:
    token = signed_token(uuid4(), "access")
    if case == "forged":
        token = signed_token(
            uuid4(), "access", key="wrong-signing-key-at-least-32-characters"
        )
    elif case == "expired":
        token = signed_token(uuid4(), "access", expired=True)
    elif case == "malformed":
        token = "broken.jwt.signature"
    elif case == "invalid_subject":
        token = signed_token(uuid4(), "access", subject="invalid-uuid")
    else:
        token = jwt.encode(
            {"sub": str(uuid4())}, settings.jwt_secret_key, algorithm="HS256"
        )
    with pytest.raises(InvalidTokenError):
        validate_access_token(token)


@pytest.mark.parametrize(
    "kind", ["missing", "malformed", "refresh", "forged", "expired"]
)
def test_api_authentication_rejects_unsafe_bearer(kind: str) -> None:
    user_id = uuid4()
    token = "broken.jwt.signature"
    if kind == "refresh":
        token = create_refresh_token(user_id)
    elif kind == "forged":
        token = signed_token(
            user_id,
            "access",
            key="wrong-signing-key-with-at-least-32-characters",
        )
    elif kind == "expired":
        token = signed_token(user_id, "access", expired=True)
    headers = {} if kind == "missing" else {"Authorization": f"Bearer {token}"}
    response = TestClient(app).get("/users/me", headers=headers)
    assert response.status_code == 401
    assert "Traceback" not in response.text
    assert token not in response.text


def test_validation_response_does_not_echo_password() -> None:
    secret = "private"
    response = TestClient(app).post(
        "/auth/register",
        json={
            "username": "test-user",
            "email": "user@example.org",
            "password": secret,
        },
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert all(
        set(error) == {"type", "loc", "msg"}
        for error in response.json()["detail"]
    )
