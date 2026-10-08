from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.service import get_current_user_id
from mini_jira.database.connection import get_session
from mini_jira.users.repository.sqlalchemy import SQLAlchemyUserRepository
from mini_jira.users.schemas import UserDTO, UserUpdate
from mini_jira.users.use_cases import (
    DeleteUserUseCase,
    GetUserUseCase,
    UpdateUserProfileUseCase,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserDTO)
async def read_user(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    repository = SQLAlchemyUserRepository(session)
    user = await GetUserUseCase(repository).execute(user_id)
    return user


@router.delete("/me", status_code=HTTPStatus.NO_CONTENT)
async def delete_user(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    repository = SQLAlchemyUserRepository(session)
    await DeleteUserUseCase(repository).execute(user_id)
    await session.commit()


@router.patch("/me", response_model=UserDTO)
async def update_user(
    request: UserUpdate,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    repository = SQLAlchemyUserRepository(session)
    user = await UpdateUserProfileUseCase(repository).execute(
        user_id,
        request,
    )
    await session.commit()
    return user
