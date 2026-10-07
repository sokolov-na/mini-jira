from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.database.models import User as UserORM
from mini_jira.users.models import User


class SQLAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        user = await self._session.get(UserORM, user_id)
        if user is not None:
            return User(
                id=user.id,
                username=user.username,
                email=user.email,
                password_hash=user.password_hash,
            )

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
        return User(
            id=user.id,
            username=username,
            email=email,
            password_hash=password_hash,
        )

    async def update(
        self,
        user_id: UUID,
        username: str,
        email: str,
    ):
        user = await self._session.get(UserORM, user_id)
        if user is not None:
            user.username = username
            user.email = email

    async def delete(
        self,
        user_id: UUID,
    ) -> None:
        user = await self._session.get(UserORM, user_id)
        if user is not None:
            await self._session.delete(user)
