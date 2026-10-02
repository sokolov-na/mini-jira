from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from pwdlib import PasswordHash
from pydantic import UUID4
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.database.connection import get_session
from mini_jira.database.errors import handle_integrity_error
from mini_jira.database.models import User
from mini_jira.exceptions import UserNotFound
from mini_jira.users.schemas import UserCreate, UserDTO, UserUpdate

router = APIRouter(prefix="/users")

password_hash = PasswordHash.recommended()


@router.post("/", status_code=HTTPStatus.CREATED, response_model=UserDTO)
async def create_user(
    user: UserCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    new_user = User(
        username=user.username,
        email=user.email,
        password_hash=password_hash.hash(user.password),
    )

    session.add(new_user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        handle_integrity_error(exc)

    return UserDTO.model_validate(new_user)


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
