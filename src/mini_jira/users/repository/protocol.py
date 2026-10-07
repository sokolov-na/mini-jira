from typing import Protocol
from uuid import UUID

from mini_jira.users.models import User


class UserRepository(Protocol):
    async def get_by_id(self, user_id: UUID) -> User | None: ...
    async def create(
        self,
        username: str,
        email: str,
        password_hash: str,
    ) -> User: ...
    async def update(
        self,
        user_id: UUID,
        username: str,
        email: str,
    ): ...
    async def delete(self, user_id: UUID) -> None: ...
