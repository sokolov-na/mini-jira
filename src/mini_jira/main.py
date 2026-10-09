from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mini_jira.auth.routes import router as auth_router
from mini_jira.config import settings
from mini_jira.exceptions import (
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidTokenError,
    UsernameAlreadyExists,
    UserNotFound,
)
from mini_jira.users.routes import router as users_router

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(users_router)
app.include_router(auth_router)


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}


@app.exception_handler(UsernameAlreadyExists)
async def username_exists_handler(
    _request: Request,
    _exc: UsernameAlreadyExists,
):
    return JSONResponse(
        status_code=HTTPStatus.CONFLICT,
        content={"detail": "Username already exists"},
    )


@app.exception_handler(EmailAlreadyExists)
async def email_exists_handler(
    _request: Request,
    _exc: EmailAlreadyExists,
):
    return JSONResponse(
        status_code=HTTPStatus.CONFLICT,
        content={"detail": "Email already exists"},
    )


@app.exception_handler(UserNotFound)
async def user_not_found(
    _request: Request,
    _exc: UserNotFound,
):
    return JSONResponse(
        status_code=HTTPStatus.NOT_FOUND,
        content={"detail": "User not found"},
    )


@app.exception_handler(InvalidTokenError)
async def invalid_token_handler(
    _request: Request,
    _exc: InvalidTokenError,
):
    return JSONResponse(
        status_code=HTTPStatus.UNAUTHORIZED,
        content={"detail": "Token is invalid"},
    )


@app.exception_handler(InvalidCredentials)
async def invalid_credentials_handler(
    _request: Request,
    _exc: InvalidCredentials,
):
    return JSONResponse(
        status_code=HTTPStatus.UNAUTHORIZED,
        content={"detail": "Invalid login or password"},
    )
