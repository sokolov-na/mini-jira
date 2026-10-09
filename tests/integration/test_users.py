import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.database.models import User as UserORM
from mini_jira.users.repository.sqlalchemy import SQLAlchemyUserRepository
from mini_jira.users.schemas import UserRegister, UserUpdate
from mini_jira.users.use_cases import (
    DeleteUserUseCase,
    RegisterUserUseCase,
    UpdateUserProfileUseCase,
)
from tests.factories import registration_data

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


async def test_repository_and_use_cases_persist_changes(
    db_session: AsyncSession,
) -> None:
    repository = SQLAlchemyUserRepository(db_session)
    user = await RegisterUserUseCase(repository).execute(
        UserRegister(**registration_data())
    )
    await db_session.commit()
    assert await repository.get_by_username(user.username) is not None
    assert await repository.get_by_email(str(user.email)) is not None
    assert await repository.get_by_id(user.id) is not None
    updated = await UpdateUserProfileUseCase(repository).execute(
        user.id, UserUpdate(username="updated-user")
    )
    await db_session.commit()
    assert updated.username == "updated-user"
    await DeleteUserUseCase(repository).execute(user.id)
    await db_session.commit()
    assert await repository.get_by_id(user.id) is None
    assert await repository.get_by_username(user.username) is None
    assert await repository.get_by_email(str(user.email)) is None


async def test_failed_transaction_rolls_back_flushed_data(
    db_session: AsyncSession,
) -> None:
    repository = SQLAlchemyUserRepository(db_session)
    await RegisterUserUseCase(repository).execute(
        UserRegister(**registration_data())
    )
    with pytest.raises(IntegrityError):
        await RegisterUserUseCase(repository).execute(
            UserRegister(**registration_data())
        )
    await db_session.rollback()
    assert (await db_session.scalars(select(UserORM))).all() == []
