from http import HTTPStatus
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.schemas import UserCredentials
from mini_jira.auth.service import (
    issue_token_pair,
    revoke_refresh_token,
    validate_refresh_token,
)
from mini_jira.auth.utils import set_refresh_token_cookie
from mini_jira.config import settings
from mini_jira.database.connection import get_session
from mini_jira.exceptions import InvalidTokenError
from mini_jira.users.repository.sqlalchemy import SQLAlchemyUserRepository
from mini_jira.users.schemas import UserRegister
from mini_jira.users.use_cases import LoginUserUseCase, RegisterUserUseCase

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = structlog.get_logger(__name__)


@router.post("/register", status_code=HTTPStatus.CREATED)
async def register_user(
    response: Response,
    request: UserRegister,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    repository = SQLAlchemyUserRepository(session)
    user = await RegisterUserUseCase(repository).execute(request)
    tokens = await issue_token_pair(session, user.id)
    await session.commit()
    set_refresh_token_cookie(response, tokens.refresh)
    logger.info("auth.register.succeeded", user_id=str(user.id))
    return {
        "access_token": tokens.access,
        "token_type": "bearer",
    }


@router.post("/login")
async def login(
    credentials: UserCredentials,
    response: Response,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    repository = SQLAlchemyUserRepository(session)
    user_id = await LoginUserUseCase(repository).execute(credentials)
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token is not None:
        await revoke_refresh_token(session, refresh_token)
    tokens = await issue_token_pair(session, user_id)
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
    logger.info("auth.refresh.rotated", user_id=str(user_id))
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
        domain=settings.refresh_cookie_domain,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )
    logger.info("auth.logout.succeeded")
