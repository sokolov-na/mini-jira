from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.database.models import User as UserORM
from mini_jira.users.models import User


class SQLAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(
        user: UserORM,
    ) -> User:
        return User(
            id=user.id,
            username=user.username,
            email=user.email,
            password_hash=user.password_hash,
        )

    async def get_by_id(
        self,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> User | None:
        statement = select(UserORM).where(UserORM.id == user_id)
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        user = await self._session.scalar(statement)
        return self._to_domain(user) if user else None

    async def get_by_email(
        self,
        email: str,
        *,
        for_update: bool = False,
    ) -> User | None:
        statement = select(UserORM).where(UserORM.email == email)
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        user = await self._session.scalar(statement)
        return self._to_domain(user) if user else None

    async def get_by_username(
        self,
        username: str,
        *,
        for_update: bool = False,
    ) -> User | None:
        statement = select(UserORM).where(UserORM.username == username)
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        user = await self._session.scalar(statement)
        return self._to_domain(user) if user else None

    async def create(
        self,
        username: str,
        email: str,
        password_hash: str,
    ) -> User:
        user = UserORM(
            username=username,
            email=email,
            password_hash=password_hash,
        )
        self._session.add(user)
        await self._session.flush()
        return self._to_domain(user)

    async def update_profile(
        self,
        user: User,
    ) -> None:
        await self._session.execute(
            update(UserORM)
            .where(UserORM.id == user.id)
            .values(
                username=user.username,
                email=user.email,
            )
        )

    async def update_password(
        self,
        user_id: UUID,
        password_hash: str,
    ) -> None:
        await self._session.execute(
            update(UserORM)
            .where(UserORM.id == user_id)
            .values(password_hash=password_hash)
        )

    async def delete(
        self,
        user: User,
    ) -> None:
        await self._session.execute(
            delete(UserORM).where(UserORM.id == user.id)
        )
