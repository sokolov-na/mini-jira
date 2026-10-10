from http import HTTPStatus

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from mini_jira.auth.routes import auth
from mini_jira.config import settings
from mini_jira.exceptions import (
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidPassword,
    InvalidTokenError,
    UsernameAlreadyExists,
    UserNotFound,
)
from mini_jira.logging.config import configure_logging
from mini_jira.logging.middleware import RequestLoggingMiddleware
from mini_jira.users.routes import users

configure_logging()

logger = structlog.get_logger(__name__)

api = FastAPI()
api.include_router(users)
api.include_router(auth)


@api.get("/health", tags=["System"], response_model=dict[str, str])
def health() -> dict[str, str]:
    return {"status": "ok"}


@api.exception_handler(UsernameAlreadyExists)
async def username_exists_handler(
    _request: Request,
    _exc: UsernameAlreadyExists,
) -> JSONResponse:
    logger.warning("users.operation.rejected", reason="username_conflict")
    return JSONResponse(
        status_code=HTTPStatus.CONFLICT,
        content={"detail": "Username already exists"},
    )


@api.exception_handler(EmailAlreadyExists)
async def email_exists_handler(
    _request: Request,
    _exc: EmailAlreadyExists,
) -> JSONResponse:
    logger.warning("users.operation.rejected", reason="email_conflict")
    return JSONResponse(
        status_code=HTTPStatus.CONFLICT,
        content={"detail": "Email already exists"},
    )


@api.exception_handler(UserNotFound)
async def user_not_found_handler(
    _request: Request,
    _exc: UserNotFound,
) -> JSONResponse:
    logger.warning("users.operation.rejected", reason="user_not_found")
    return JSONResponse(
        status_code=HTTPStatus.NOT_FOUND,
        content={"detail": "User not found"},
    )


@api.exception_handler(InvalidTokenError)
async def invalid_token_handler(
    _request: Request,
    _exc: InvalidTokenError,
) -> JSONResponse:
    logger.warning("auth.token.rejected", reason="invalid_or_missing_token")
    return JSONResponse(
        status_code=HTTPStatus.UNAUTHORIZED,
        content={"detail": "Token is invalid"},
    )


@api.exception_handler(InvalidCredentials)
async def invalid_credentials_handler(
    _request: Request,
    _exc: InvalidCredentials,
) -> JSONResponse:
    return JSONResponse(
        status_code=HTTPStatus.UNAUTHORIZED,
        content={"detail": "Invalid login or password"},
    )


@api.exception_handler(InvalidPassword)
async def invalid_password_handler(
    _request: Request,
    _exc: InvalidPassword,
) -> JSONResponse:
    return JSONResponse(
        status_code=HTTPStatus.BAD_REQUEST,
        content={"detail": "Invalid password"},
    )


@api.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(
    _request: Request,
    _exc: SQLAlchemyError,
) -> JSONResponse:
    logger.error(
        "database.unexpected_error",
        component="database",
        exception_type=type(_exc).__name__,
        exc_info=(type(_exc), _exc, _exc.__traceback__),
    )
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@api.exception_handler(Exception)
async def unhandled_exception_handler(
    _request: Request,
    _exc: Exception,
) -> JSONResponse:
    logger.error(
        "application.unexpected_error",
        component="application",
        exception_type=type(_exc).__name__,
        exc_info=(type(_exc), _exc, _exc.__traceback__),
    )
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@api.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors: list[dict[str, object]] = []
    for error in exc.errors():
        email_error = (
            error["loc"][-1:] == ("email",) and error["type"] != "missing"
        )
        errors.append(
            {
                "type": "email_invalid" if email_error else error["type"],
                "loc": error["loc"],
                "msg": "Email address is invalid"
                if email_error
                else error["msg"],
            }
        )
    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_CONTENT,
        content={"detail": errors},
    )


app = CORSMiddleware(
    RequestLoggingMiddleware(api),
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
