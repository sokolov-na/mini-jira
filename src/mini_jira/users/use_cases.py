from uuid import UUID

import structlog
from pwdlib import PasswordHash
from pydantic import ValidationError

from mini_jira.exceptions import (
    InvalidCredentials,
    InvalidPassword,
    InvalidTokenError,
    UserNotFound,
)
from mini_jira.users.models import User
from mini_jira.users.repository.protocol import UserRepository
from mini_jira.users.schemas import (
    UserCredentials,
    UserDTO,
    UserPasswordReset,
    UserPasswordResetConfirm,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserRegister,
    normalize_email,
)

_hasher = PasswordHash.recommended()
logger = structlog.get_logger(__name__)


async def _find_user_by_login(
    repository: UserRepository, login: str
) -> User | None:
    try:
        email = normalize_email(login)
    except ValidationError:
        return await repository.get_by_username(login, for_update=True)
    return await repository.get_by_email(email, for_update=True)


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
        user = await _find_user_by_login(self._repository, credentials.login)

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
        data: UserProfileUpdate,
    ) -> UserDTO:
        user = await self._repository.get_by_id(user_id, for_update=True)
        if user is None:
            raise UserNotFound()
        if data.username is not None:
            user.username = data.username
        if data.email is not None:
            user.email = data.email
        await self._repository.update_profile(user)
        return UserDTO.model_validate(user)


class UpdateUserPasswordUseCase:
    def __init__(
        self,
        repository: UserRepository,
    ) -> None:
        self._repository = repository

    async def execute(
        self,
        user_id: UUID,
        data: UserPasswordUpdate,
    ) -> None:
        user = await self._repository.get_by_id(user_id, for_update=True)
        if user is None:
            raise UserNotFound()
        if not _hasher.verify(
            data.current_password,
            user.password_hash,
        ):
            logger.warning(
                "auth.password_update.failed", reason="invalid_password"
            )
            raise InvalidPassword()
        await self._repository.update_password(
            user.id, _hasher.hash(data.new_password)
        )


class ResetUserPasswordUseCase:
    def __init__(
        self,
        repository: UserRepository,
    ) -> None:
        self._repository = repository

    async def execute(
        self,
        credentials: UserPasswordReset,
    ) -> UserDTO:
        user = await _find_user_by_login(self._repository, credentials.login)

        if user is None:
            logger.warning(
                "auth.password_reset.failed", reason="user_not_found"
            )
            raise UserNotFound()

        return UserDTO.model_validate(user)


class ResetUserPasswordConfirmUseCase:
    def __init__(
        self,
        repository: UserRepository,
    ) -> None:
        self._repository = repository

    async def execute(
        self,
        user_id: UUID,
        data: UserPasswordResetConfirm,
    ) -> None:
        user = await self._repository.get_by_id(user_id, for_update=True)
        if user is None:
            raise InvalidTokenError()
        await self._repository.update_password(
            user.id, _hasher.hash(data.new_password)
        )


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
