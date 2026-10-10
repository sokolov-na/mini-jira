from datetime import UTC, datetime
from typing import Annotated, NamedTuple
from uuid import UUID

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.tokens import (
    PASSWORD_RESET_TOKEN_LIFETIME,
    REFRESH_TOKEN_LIFETIME,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_password_reset_token,
    hash_token,
)
from mini_jira.database.models import PasswordResetToken, RefreshToken, User
from mini_jira.exceptions import InvalidTokenError, UserNotFound
from mini_jira.users.repository.sqlalchemy import SQLAlchemyUserRepository
from mini_jira.users.schemas import (
    UserPasswordReset,
    UserPasswordResetConfirm,
    UserPasswordUpdate,
)
from mini_jira.users.use_cases import (
    ResetUserPasswordConfirmUseCase,
    ResetUserPasswordUseCase,
    UpdateUserPasswordUseCase,
)

logger = structlog.get_logger(__name__)


async def lock_user(session: AsyncSession, user_id: UUID) -> None:
    locked_id = await session.scalar(
        select(User.id).where(User.id == user_id).with_for_update()
    )
    if locked_id is None:
        raise InvalidTokenError()


async def save_refresh_token(
    session: AsyncSession,
    user_id: UUID,
    token: str,
) -> None:
    refresh_token = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + REFRESH_TOKEN_LIFETIME,
    )
    session.add(refresh_token)


async def revoke_refresh_token(
    session: AsyncSession,
    token: str,
) -> None:
    user_id = await session.scalar(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(token))
        .values(revoked=True)
        .returning(RefreshToken.user_id)
    )
    if user_id is None:
        return
    logger.info("auth.refresh.revocation_requested", user_id=str(user_id))


async def revoke_all_refresh_tokens(
    session: AsyncSession,
    user_id: UUID,
) -> None:
    await lock_user(session, user_id)
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked.is_(False),
        )
        .values(revoked=True)
    )


async def validate_refresh_token(
    session: AsyncSession,
    token: str,
) -> UUID:
    payload = decode_token(token, expected_type="refresh")
    try:
        user_id = UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError from exc
    await lock_user(session, user_id)
    refresh_token = await session.scalar(
        select(RefreshToken)
        .execution_options(populate_existing=True)
        .where(
            RefreshToken.token_hash == hash_token(token),
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


def validate_access_token(token: str) -> UUID:
    payload = decode_token(token, expected_type="access")
    try:
        user_id = UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError from exc
    return user_id


security = HTTPBearer()


def get_current_user_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(security),
    ],
) -> UUID:
    return validate_access_token(credentials.credentials)


class TokenPair(NamedTuple):
    access: str
    refresh: str


async def issue_token_pair(
    session: AsyncSession,
    user_id: UUID,
) -> TokenPair:
    await lock_user(session, user_id)
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


async def save_password_reset_token(
    session: AsyncSession,
    user_id: UUID,
    token: str,
) -> None:
    await lock_user(session, user_id)
    password_reset_token = PasswordResetToken(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + PASSWORD_RESET_TOKEN_LIFETIME,
    )
    session.add(password_reset_token)


async def invalidate_password_reset_tokens(
    session: AsyncSession,
    user_id: UUID,
) -> None:
    await lock_user(session, user_id)
    await session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
        )
        .values(consumed=True)
    )


async def consume_password_reset_token(
    session: AsyncSession,
    token: str,
) -> UUID:
    token_hash = hash_token(token)
    user_id = await session.scalar(
        select(PasswordResetToken.user_id).where(
            PasswordResetToken.token_hash == token_hash
        )
    )
    if user_id is None:
        raise InvalidTokenError()
    await lock_user(session, user_id)
    consumed_user_id = await session.scalar(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.consumed.is_(False),
            PasswordResetToken.expires_at > datetime.now(UTC),
        )
        .values(consumed=True)
        .returning(PasswordResetToken.user_id)
    )
    if consumed_user_id is None:
        raise InvalidTokenError()
    return consumed_user_id


async def change_password(
    session: AsyncSession, user_id: UUID, data: UserPasswordUpdate
) -> TokenPair:
    await UpdateUserPasswordUseCase(SQLAlchemyUserRepository(session)).execute(
        user_id, data
    )
    await invalidate_password_reset_tokens(session, user_id)
    await revoke_all_refresh_tokens(session, user_id)
    return await issue_token_pair(session, user_id)


async def prepare_password_reset(
    session: AsyncSession, data: UserPasswordReset
) -> tuple[str, str] | None:
    try:
        user = await ResetUserPasswordUseCase(
            SQLAlchemyUserRepository(session)
        ).execute(data)
    except UserNotFound:
        return None
    token = generate_password_reset_token()
    await invalidate_password_reset_tokens(session, user.id)
    await save_password_reset_token(session, user.id, token)
    return user.email, token


async def complete_password_reset(
    session: AsyncSession, data: UserPasswordResetConfirm
) -> None:
    user_id = await consume_password_reset_token(
        session, data.password_reset_token
    )
    await ResetUserPasswordConfirmUseCase(
        SQLAlchemyUserRepository(session)
    ).execute(user_id, data)
    await invalidate_password_reset_tokens(session, user_id)
    await revoke_all_refresh_tokens(session, user_id)
