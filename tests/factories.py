from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from mini_jira.config import settings

PASSWORD = "TestPassword123!"


@dataclass(frozen=True)
class RegisteredUser:
    id: UUID
    username: str
    email: str
    password: str
    access: str
    refresh: str


def registration_data(index: int = 1) -> dict[str, str]:
    return {
        "username": f"test-user-{index}",
        "email": f"user{index}@example.org",
        "password": PASSWORD,
    }


def signed_token(
    user_id: UUID,
    kind: str = "refresh",
    *,
    expired: bool = False,
    subject: str | None = None,
    key: str | None = None,
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id) if subject is None else subject,
            "type": kind,
            "iat": now - timedelta(minutes=2),
            "exp": now + timedelta(minutes=-1 if expired else 10),
            "jti": str(uuid4()),
        },
        key or settings.jwt_secret_key,
        algorithm="HS256",
    )
