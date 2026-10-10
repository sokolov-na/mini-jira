import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.database.models import User as UserORM
from mini_jira.users.repository.sqlalchemy import SQLAlchemyUserRepository
from mini_jira.users.schemas import UserProfileUpdate, UserRegister
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
        user.id, UserProfileUpdate(username="updated-user")
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


async def test_narrow_updates_do_not_restore_stale_user_fields(
    db_session: AsyncSession,
) -> None:
    repository = SQLAlchemyUserRepository(db_session)
    created = await RegisterUserUseCase(repository).execute(
        UserRegister(**registration_data())
    )
    stale = await repository.get_by_id(created.id)
    assert stale is not None
    await repository.update_password(created.id, "new-test-hash")
    stale.username = "updated-profile"
    await repository.update_profile(stale)
    current = await repository.get_by_id(created.id)
    assert current is not None and current.password_hash == "new-test-hash"
    assert current.username == "updated-profile"
    current.email = "new@example.org"
    await repository.update_profile(current)
    await repository.update_password(stale.id, "another-test-hash")
    current = await repository.get_by_id(created.id)
    assert current is not None and current.email == "new@example.org"
    assert current.username == "updated-profile"
    assert current.password_hash == "another-test-hash"
