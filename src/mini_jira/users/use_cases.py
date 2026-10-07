from uuid import UUID

from pwdlib import PasswordHash

from mini_jira.exceptions import UserNotFound
from mini_jira.users.repository.protocol import UserRepository
from mini_jira.users.schemas import UserDTO, UserRegister, UserUpdate

_hasher = PasswordHash.recommended()


class RegisterUserUseCase:
    def __init__(
        self,
        repository: UserRepository,
    ) -> None:
        self._repository = repository

    async def execute(self, data: UserRegister) -> UserDTO:
        user = await self._repository.create(
            username=data.username,
            email=data.email,
            password_hash=_hasher.hash(data.password),
        )
        return UserDTO.model_validate(user)


class GetUserUseCase:
    def __init__(
        self,
        repository: UserRepository,
    ) -> None:
        self._repository = repository

    async def execute(self, user_id: UUID) -> UserDTO:
        user = await self._repository.get_by_id(user_id)
        if user is None:
            raise UserNotFound()
        return UserDTO.model_validate(user)


class DeleteUserUseCase:
    def __init__(
        self,
        repository: UserRepository,
    ) -> None:
        self._repository = repository

    async def execute(self, user_id: UUID) -> None:
        user = await self._repository.get_by_id(user_id)
        if user is None:
            raise UserNotFound()
        await self._repository.delete(user_id)


class UpdateUserProfileUseCase:
    def __init__(
        self,
        repository: UserRepository,
    ) -> None:
        self._repository = repository

    async def execute(
        self,
        user_id: UUID,
        data: UserUpdate,
    ):
        user = await self._repository.get_by_id(user_id)
        if user is None:
            raise UserNotFound()
        email = user.email if data.email is None else data.email
        username = user.username if data.username is None else data.username
        await self._repository.update(
            user_id=user_id,
            username=username,
            email=email,
        )
