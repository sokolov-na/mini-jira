from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.schemas import UserRegister
from mini_jira.auth.service import save_refresh_token
from mini_jira.auth.tokens import create_access_token, create_refresh_token
from mini_jira.database.connection import get_session
from mini_jira.database.errors import handle_integrity_error
from mini_jira.database.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

password_hash = PasswordHash.recommended()


@router.post("/register", status_code=HTTPStatus.CREATED)
async def register_user(
    response: Response,
    user: UserRegister,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    new_user = User(
        username=user.username,
        email=user.email,
        password_hash=password_hash.hash(user.password),
    )

    session.add(new_user)

    try:
        await session.flush()

        refresh_token = create_refresh_token(new_user.id)
        access_token = create_access_token(new_user.id)

        await save_refresh_token(
            session,
            new_user.id,
            refresh_token,
        )

        await session.commit()

    except IntegrityError as exc:
        await session.rollback()
        handle_integrity_error(exc)
        raise

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # TEMPORARY
        samesite="lax",
        path="/auth",
        max_age=7 * 24 * 60 * 60,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/login")
async def login(): ...


@router.post("/refresh")
async def refresh_tokens(): ...


@router.post("/logout")
async def logout(): ...
