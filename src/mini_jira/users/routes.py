from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.database.connection import get_session
from mini_jira.database.models import User
from mini_jira.exceptions import UserNotFound
from mini_jira.users.schemas import UserDTO, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}", response_model=UserDTO)
async def read_user(
    user_id: UUID4,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFound()
    return UserDTO.model_validate(user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID4,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFound()
    await session.delete(user)
    await session.commit()


@router.patch("/{user_id}")
async def update_user(
    user_id: UUID4,
    data: UserUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFound()
    data_dict = data.model_dump(exclude_unset=True)
    if data_dict == {}:
        return
    for field, value in data_dict.items():
        setattr(user, field, value)

    await session.commit()
