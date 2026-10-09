from uuid import UUID

import structlog
from email_validator import EmailNotValidError, validate_email
from pwdlib import PasswordHash

from mini_jira.auth.schemas import UserCredentials
from mini_jira.exceptions import InvalidCredentials, UserNotFound
from mini_jira.users.repository.protocol import UserRepository
from mini_jira.users.schemas import UserDTO, UserRegister, UserUpdate

_hasher = PasswordHash.recommended()
logger = structlog.get_logger(__name__)


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


class LoginUserUseCase:
    def __init__(
        self,
        repository: UserRepository,
    ) -> None:
        self._repository = repository

    async def execute(self, credentials: UserCredentials) -> UUID:
        try:
            email = validate_email(credentials.login).normalized
        except EmailNotValidError:
            user = await self._repository.get_by_username(
                credentials.login,
            )
        else:
            user = await self._repository.get_by_email(email)

        if user is None:
            logger.warning("auth.login.failed", reason="user_not_found")
            raise InvalidCredentials()

        if not _hasher.verify(
            credentials.password,
            user.password_hash,
        ):
            logger.warning("auth.login.failed", reason="invalid_password")
            raise InvalidCredentials()

        logger.info("auth.login.succeeded", user_id=str(user.id))
        return user.id


class GetUserUseCase:
    def __init__(
        self,
        repository: UserRepository,
    ) -> None:
        self._repository = repository

    async def execute(
        self,
        user_id: UUID,
    ) -> UserDTO:
        user = await self._repository.get_by_id(user_id)
        if user is None:
            raise UserNotFound()
        return UserDTO.model_validate(user)


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
    ) -> UserDTO:
        user = await self._repository.get_by_id(user_id)
        if user is None:
            raise UserNotFound()
        if data.username is not None:
            user.username = data.username
        if data.email is not None:
            user.email = data.email
        await self._repository.update(user)
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
        await self._repository.delete(user)
