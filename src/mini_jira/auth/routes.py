from http import HTTPStatus
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Request, Response
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.schemas import UserCredentials, UserRegister
from mini_jira.auth.service import (
    issue_token_pair,
    revoke_refresh_token,
    validate_refresh_token,
)
from mini_jira.auth.utils import set_refresh_token_cookie
from mini_jira.database.connection import get_session
from mini_jira.database.models import User
from mini_jira.exceptions import InvalidCredentials, InvalidTokenError

router = APIRouter(prefix="/auth", tags=["auth"])

password_hash = PasswordHash.recommended()


@router.post("/register", status_code=HTTPStatus.CREATED)
async def register_user(
    response: Response,
    new_user: UserRegister,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    # users use case start
    user = User(
        username=new_user.username,
        email=new_user.email,
        password_hash=password_hash.hash(new_user.password),
    )
    session.add(user)
    # users use case end
    await session.flush()
    tokens = await issue_token_pair(session, user.id)
    await session.commit()
    set_refresh_token_cookie(response, tokens.refresh)
    return {
        "access_token": tokens.access,
        "token_type": "bearer",
    }


@router.post("/login")
async def login(
    credentials: UserCredentials,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    # users use case start
    user = None
    try:
        email = validate_email(credentials.login).normalized
        user = await session.scalar(
            select(User).where(User.email == email),
        )
    except EmailNotValidError:
        user = await session.scalar(
            select(User).where(User.username == credentials.login)
        )
    if user is None:
        raise InvalidCredentials()
    if not password_hash.verify(credentials.password, user.password_hash):
        raise InvalidCredentials()
    # users use case end
    tokens = await issue_token_pair(session, user.id)
    await session.commit()
    set_refresh_token_cookie(response, tokens.refresh)
    return {
        "access_token": tokens.access,
        "token_type": "bearer",
    }


@router.post("/refresh")
async def refresh_tokens(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token is None:
        raise InvalidTokenError()
    user_id = await validate_refresh_token(session, refresh_token)
    await revoke_refresh_token(session, refresh_token)
    tokens = await issue_token_pair(session, user_id)
    await session.commit()
    set_refresh_token_cookie(response, tokens.refresh)
    return {
        "access_token": tokens.access,
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token is None:
        return
    await revoke_refresh_token(session, refresh_token)
    await session.commit()
    response.delete_cookie(
        key="refresh_token",
        path="/auth",
    )
