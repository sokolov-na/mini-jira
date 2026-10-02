from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mini_jira.exceptions import (
    EmailAlreadyExists,
    UsernameAlreadyExists,
    UserNotFound,
)
from mini_jira.users.routes import router as users_router

app = FastAPI()
app.include_router(users_router)


@app.get("/health")
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
