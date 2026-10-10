from typing import Protocol
from uuid import UUID

from mini_jira.users.models import User


class UserRepository(Protocol):
    async def get_by_id(
        self,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> User | None: ...
    async def get_by_email(
        self,
        email: str,
        *,
        for_update: bool = False,
    ) -> User | None: ...
    async def get_by_username(
        self,
        username: str,
        *,
        for_update: bool = False,
    ) -> User | None: ...
    async def create(
        self,
        username: str,
        email: str,
        password_hash: str,
    ) -> User: ...
    async def update_profile(
        self,
        user: User,
    ) -> None: ...
    async def update_password(
        self,
        user_id: UUID,
        password_hash: str,
    ) -> None: ...
    async def delete(
        self,
        user: User,
    ) -> None: ...
