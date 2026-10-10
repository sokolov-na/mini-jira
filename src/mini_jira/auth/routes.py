from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.email import send_password_reset_email
from mini_jira.auth.schemas import AccessTokenResponse
from mini_jira.auth.service import (
    change_password,
    complete_password_reset,
    get_current_user_id,
    issue_token_pair,
    prepare_password_reset,
    revoke_refresh_token,
    validate_refresh_token,
)
from mini_jira.auth.utils import (
    delete_refresh_token_cookie,
    set_refresh_token_cookie,
)
from mini_jira.database.connection import get_session
from mini_jira.exceptions import InvalidTokenError
from mini_jira.users.repository.sqlalchemy import SQLAlchemyUserRepository
from mini_jira.users.schemas import (
    UserCredentials,
    UserPasswordReset,
    UserPasswordResetConfirm,
    UserPasswordUpdate,
    UserRegister,
)
from mini_jira.users.use_cases import (
    LoginUserUseCase,
    RegisterUserUseCase,
)

auth = APIRouter(prefix="/auth", tags=["Authentication"])
password = APIRouter(prefix="/password", tags=["Password"])

logger = structlog.get_logger(__name__)


@auth.post(
    "/register",
    status_code=HTTPStatus.CREATED,
    response_model=AccessTokenResponse,
)
async def register_user(
    response: Response,
    request: UserRegister,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccessTokenResponse:
    repository = SQLAlchemyUserRepository(session)
    user = await RegisterUserUseCase(repository).execute(request)
    tokens = await issue_token_pair(session, user.id)
    await session.commit()
    set_refresh_token_cookie(response, tokens.refresh)
    logger.info("auth.register.succeeded", user_id=str(user.id))
    return AccessTokenResponse(access_token=tokens.access)


@auth.post("/login", response_model=AccessTokenResponse)
async def login(
    credentials: UserCredentials,
    response: Response,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccessTokenResponse:
    repository = SQLAlchemyUserRepository(session)
    user_id = await LoginUserUseCase(repository).execute(credentials)
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token is not None:
        await revoke_refresh_token(session, refresh_token)
    tokens = await issue_token_pair(session, user_id)
    await session.commit()
    set_refresh_token_cookie(response, tokens.refresh)
    return AccessTokenResponse(access_token=tokens.access)


@auth.post("/refresh", response_model=AccessTokenResponse)
async def refresh_tokens(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccessTokenResponse:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token is None:
        raise InvalidTokenError()
    user_id = await validate_refresh_token(session, refresh_token)
    await revoke_refresh_token(session, refresh_token)
    tokens = await issue_token_pair(session, user_id)
    await session.commit()
    set_refresh_token_cookie(response, tokens.refresh)
    logger.info("auth.refresh.rotated", user_id=str(user_id))
    return AccessTokenResponse(access_token=tokens.access)


@auth.post("/logout", response_model=type(None))
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token is None:
        return
    await revoke_refresh_token(session, refresh_token)
    await session.commit()
    delete_refresh_token_cookie(response)
    logger.info("auth.logout.succeeded")


@password.patch("/update", response_model=AccessTokenResponse)
async def update_password(
    request: UserPasswordUpdate,
    response: Response,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccessTokenResponse:
    tokens = await change_password(session, user_id, request)
    await session.commit()
    set_refresh_token_cookie(response, tokens.refresh)
    logger.info("users.password.updated", user_id=str(user_id))
    return AccessTokenResponse(access_token=tokens.access)


@password.post(
    "/reset", status_code=HTTPStatus.ACCEPTED, response_model=type(None)
)
async def reset_password(
    request: UserPasswordReset,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    delivery = await prepare_password_reset(session, request)
    if delivery is None:
        return
    email, token = delivery
    await session.commit()
    await send_password_reset_email(email, token)


@password.post("/reset/confirm", response_model=type(None))
async def confirm_password_reset(
    request: UserPasswordResetConfirm,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await complete_password_reset(session, request)
    await session.commit()


auth.include_router(password)
