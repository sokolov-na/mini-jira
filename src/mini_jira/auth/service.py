from datetime import UTC, datetime
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.tokens import (
    REFRESH_TOKEN_LIFETIME,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_refresh_token,
)
from mini_jira.database.models import RefreshToken
from mini_jira.exceptions import InvalidTokenError


async def save_refresh_token(
    session: AsyncSession,
    user_id: UUID,
    token: str,
) -> None:
    refresh_token = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(token),
        expires_at=datetime.now(UTC) + REFRESH_TOKEN_LIFETIME,
    )
    session.add(refresh_token)


async def revoke_refresh_token(
    session: AsyncSession,
    token: str,
) -> None:
    refresh_token: RefreshToken | None = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(token),
        )
    )
    if refresh_token is None:
        return
    refresh_token.revoked = True


async def validate_refresh_token(
    session: AsyncSession,
    token: str,
) -> UUID:
    payload = decode_token(token, expected_type="refresh")
    try:
        user_id = UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError from exc
    refresh_token = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(token),
        )
    )
    if (
        refresh_token is None
        or refresh_token.revoked
        or refresh_token.expires_at <= datetime.now(UTC)
        or refresh_token.user_id != user_id
    ):
        raise InvalidTokenError
    return user_id


class TokenPair(NamedTuple):
    access: str
    refresh: str


async def issue_token_pair(
    session: AsyncSession,
    user_id: UUID,
) -> TokenPair:
    refresh_token = create_refresh_token(user_id)
    access_token = create_access_token(user_id)
    await save_refresh_token(
        session,
        user_id,
        refresh_token,
    )
    return TokenPair(
        refresh=refresh_token,
        access=access_token,
    )
