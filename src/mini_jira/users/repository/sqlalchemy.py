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
    ) -> User | None:
        user = await self._session.get(UserORM, user_id)
        return self._to_domain(user) if user else None

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:
        user = await self._session.scalar(
            select(UserORM).where(UserORM.email == email)
        )
        return self._to_domain(user) if user else None

    async def get_by_username(
        self,
        username: str,
    ) -> User | None:
        user = await self._session.scalar(
            select(UserORM).where(UserORM.username == username)
        )
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

    async def update(
        self,
        user: User,
    ) -> None:
        await self._session.execute(
            update(UserORM)
            .where(UserORM.id == user.id)
            .values(username=user.username, email=user.email)
        )

    async def delete(
        self,
        user: User,
    ) -> None:
        await self._session.execute(
            delete(UserORM).where(UserORM.id == user.id)
        )
