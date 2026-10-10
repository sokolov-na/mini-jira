from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.service import get_current_user_id
from mini_jira.database.connection import get_session
from mini_jira.users.repository.sqlalchemy import SQLAlchemyUserRepository
from mini_jira.users.schemas import UserDTO, UserProfileUpdate
from mini_jira.users.use_cases import (
    DeleteUserUseCase,
    GetUserUseCase,
    UpdateUserProfileUseCase,
)

users = APIRouter(prefix="/users", tags=["Users"])
logger = structlog.get_logger(__name__)


@users.get("/me", response_model=UserDTO)
async def read_user(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserDTO:
    repository = SQLAlchemyUserRepository(session)
    user = await GetUserUseCase(repository).execute(user_id)
    return user


@users.delete("/me", status_code=HTTPStatus.NO_CONTENT, response_model=None)
async def delete_user(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    repository = SQLAlchemyUserRepository(session)
    await DeleteUserUseCase(repository).execute(user_id)
    await session.commit()
    logger.info("users.profile.deleted", user_id=str(user_id))


@users.patch("/me", response_model=UserDTO)
async def update_user(
    request: UserProfileUpdate,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserDTO:
    repository = SQLAlchemyUserRepository(session)
    user = await UpdateUserProfileUseCase(repository).execute(
        user_id,
        request,
    )
    await session.commit()
    logger.info("users.profile.updated", user_id=str(user_id))
    return user
