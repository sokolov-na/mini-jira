import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Final, Literal
from uuid import UUID, uuid4

import jwt

from mini_jira.config import settings
from mini_jira.exceptions import InvalidTokenError

ALGORITHM: Final = "HS256"
ACCESS_TOKEN_LIFETIME: Final = timedelta(minutes=15)
REFRESH_TOKEN_LIFETIME: Final = timedelta(days=7)
PASSWORD_RESET_TOKEN_LIFETIME: Final = timedelta(minutes=10)


def _create_token(
    user_id: UUID,
    token_type: Literal["access", "refresh"],
    lifetime: timedelta,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
        "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        key=settings.jwt_secret_key,
        algorithm=ALGORITHM,
    )


def create_refresh_token(user_id: UUID) -> str:
    return _create_token(
        user_id=user_id,
        token_type="refresh",
        lifetime=REFRESH_TOKEN_LIFETIME,
    )


def create_access_token(user_id: UUID) -> str:
    return _create_token(
        user_id=user_id,
        token_type="access",
        lifetime=ACCESS_TOKEN_LIFETIME,
    )


def decode_token(
    token: str,
    expected_type: Literal["access", "refresh"],
) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[ALGORITHM],
            options={
                "require": [
                    "sub",
                    "type",
                    "iat",
                    "exp",
                    "jti",
                ],
            },
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError from exc
    if payload["type"] != expected_type:
        raise InvalidTokenError
    return payload


def generate_password_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
