from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.service import (
    issue_token_pair,
    revoke_refresh_token,
    validate_refresh_token,
)
from mini_jira.auth.tokens import hash_token
from mini_jira.database.models import RefreshToken
from mini_jira.exceptions import InvalidTokenError
from mini_jira.users.repository.sqlalchemy import SQLAlchemyUserRepository
from mini_jira.users.schemas import UserRegister
from mini_jira.users.use_cases import RegisterUserUseCase
from tests.factories import registration_data, signed_token

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


@pytest.mark.parametrize(
    "failure", ["missing", "revoked", "expired", "wrong_user"]
)
async def test_refresh_service_checks_database_state(
    failure: str,
    db_session: AsyncSession,
) -> None:
    user = await RegisterUserUseCase(
        SQLAlchemyUserRepository(db_session)
    ).execute(UserRegister(**registration_data()))
    tokens = await issue_token_pair(db_session, user.id)
    await db_session.commit()
    assert await validate_refresh_token(db_session, tokens.refresh) == user.id
    record = await db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_token(tokens.refresh)
        )
    )
    assert record
    if failure == "missing":
        token = signed_token(user.id)
    else:
        token = tokens.refresh
        if failure == "revoked":
            await revoke_refresh_token(db_session, token)
        elif failure == "expired":
            record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        else:
            other = await RegisterUserUseCase(
                SQLAlchemyUserRepository(db_session)
            ).execute(UserRegister(**registration_data(2)))
            record.user_id = other.id
        await db_session.commit()
    with pytest.raises(InvalidTokenError):
        await validate_refresh_token(db_session, token)


async def test_unknown_revocation_is_noop(db_session: AsyncSession) -> None:
    await revoke_refresh_token(db_session, signed_token(uuid4()))
    await db_session.commit()
