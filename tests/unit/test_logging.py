import asyncio
import json
from collections.abc import Iterator
from io import StringIO
from typing import cast
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import httpx2 as httpx
import pytest
import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from psycopg import Error
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, StatementError
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from mini_jira.auth.routes import logout, refresh_tokens, register_user
from mini_jira.auth.service import TokenPair
from mini_jira.config import settings
from mini_jira.database.connection import get_session
from mini_jira.exceptions import (
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidTokenError,
    UsernameAlreadyExists,
    UserNotFound,
)
from mini_jira.logging.config import configure_logging
from mini_jira.logging.middleware import RequestLoggingMiddleware
from mini_jira.main import api, app
from mini_jira.users.routes import delete_user, update_user
from mini_jira.users.schemas import (
    UserCredentials,
    UserDTO,
    UserProfileUpdate,
    UserRegister,
)
from mini_jira.users.use_cases import LoginUserUseCase

ORIGIN = "https://frontend.example.com"
SECRET = "sensitive-password-jwt-cookie-email@example.com"
pytestmark = pytest.mark.unit


@pytest.fixture
def output() -> Iterator[StringIO]:
    stream = StringIO()
    configure_logging()
    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=False,
    )
    structlog.contextvars.clear_contextvars()
    yield stream
    structlog.contextvars.clear_contextvars()
    configure_logging()
    structlog.configure(cache_logger_on_first_use=False)


def events(output: StringIO) -> list[dict[str, object]]:
    return [
        cast("dict[str, object]", json.loads(line))
        for line in output.getvalue().splitlines()
    ]


def http_events(output: StringIO) -> list[dict[str, object]]:
    return [item for item in events(output) if item["event"] == "http.request"]


@pytest.fixture
def application() -> ASGIApp:
    test_api = FastAPI()
    test_api.exception_handlers.update(api.exception_handlers)
    test_api.include_router(api.router)

    @test_api.get("/crash")
    async def crash() -> None:
        raise RuntimeError(SECRET)

    @test_api.get("/database-crash")
    async def database_crash() -> None:
        raise StatementError(
            SECRET,
            f"SELECT '{SECRET}'",
            {"password": SECRET},
            ValueError(SECRET),
        )

    @test_api.api_route("/context", methods=["GET", "POST"])
    async def context(request: Request) -> dict[str, str]:
        before = str(structlog.contextvars.get_contextvars()["request_id"])
        await asyncio.sleep(0.001)
        after = str(structlog.contextvars.get_contextvars()["request_id"])
        structlog.get_logger().info("test.context", before=before, after=after)
        return {"request_id": after, "path": request.url.path}

    @test_api.get("/status/{code}")
    async def status(code: int) -> Response:
        return Response(status_code=code)

    @test_api.get("/validation")
    async def validation(number: int) -> dict[str, int]:
        return {"number": number}

    exceptions = {
        "credentials": InvalidCredentials,
        "token": InvalidTokenError,
        "user": UserNotFound,
        "username": UsernameAlreadyExists,
        "email": EmailAlreadyExists,
    }

    @test_api.get("/domain/{name}")
    async def domain(name: str) -> None:
        raise exceptions[name]()

    @test_api.get("/expected-conflict")
    async def expected_conflict(
        _session: object = Depends(get_session),
    ) -> None:
        original = Mock(spec=Error)
        original.diag.constraint_name = "users_username_key"
        raise IntegrityError(SECRET, {"password": SECRET}, original)

    return RequestLoggingMiddleware(
        CORSMiddleware(
            test_api,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
    )


def test_health_request_id_and_fields(output: StringIO) -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    (event,) = http_events(output)
    assert event["request_id"] == response.headers["X-Request-ID"]
    UUID(str(event["request_id"]))
    assert event["level"] == "info"
    assert event["method"] == "GET"
    assert event["path"] == "/health"
    assert event["status_code"] == 200
    assert isinstance(event["duration_ms"], (float, int))
    assert event["duration_ms"] >= 0
    assert "timestamp" in event


@pytest.mark.parametrize("path", ["/docs", "/openapi.json", "/unknown"])
def test_non_api_routes_are_not_logged(path: str, output: StringIO) -> None:
    TestClient(app).get(path)
    assert not http_events(output)


def test_parallel_contexts(application: ASGIApp, output: StringIO) -> None:
    async def run() -> list[httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            return await asyncio.gather(
                *(client.get("/context") for _ in range(10))
            )

    responses = asyncio.run(run())
    ids = {response.headers["X-Request-ID"] for response in responses}
    assert len(ids) == 10
    assert len(http_events(output)) == 10
    assert {item["request_id"] for item in http_events(output)} == ids
    for item in events(output):
        if item["event"] == "test.context":
            assert item["before"] == item["after"] == item["request_id"]
    assert structlog.contextvars.get_contextvars() == {}


@pytest.mark.parametrize(
    ("code", "level"),
    [
        (200, "info"),
        (302, "info"),
        (401, "warning"),
        (422, "warning"),
        (500, "error"),
        (503, "error"),
    ],
)
def test_http_levels(
    code: int, level: str, application: ASGIApp, output: StringIO
) -> None:
    TestClient(application).get(f"/status/{code}", follow_redirects=False)
    (event,) = http_events(output)
    assert event["level"] == level
    assert event["status_code"] == code


@pytest.mark.parametrize(
    ("path", "name", "exception_type"),
    [
        ("/crash", "application.unexpected_error", "RuntimeError"),
        ("/database-crash", "database.unexpected_error", "StatementError"),
    ],
)
def test_unexpected_errors(
    path: str,
    name: str,
    exception_type: str,
    application: ASGIApp,
    output: StringIO,
) -> None:
    response = TestClient(application, raise_server_exceptions=False).get(
        path, headers={"Origin": ORIGIN}
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]
    (diagnostic,) = [item for item in events(output) if item["event"] == name]
    (http,) = http_events(output)
    assert diagnostic["request_id"] == http["request_id"]
    assert http["request_id"] == response.headers["X-Request-ID"]
    assert diagnostic["level"] == http["level"] == "error"
    assert diagnostic["exception_type"] == exception_type
    assert "Traceback" in str(diagnostic["exception"])
    assert exception_type in str(diagnostic["exception"])
    assert len([item for item in events(output) if "exception" in item]) == 1
    assert SECRET not in output.getvalue()
    assert structlog.contextvars.get_contextvars() == {}


def test_server_error_still_propagates(
    application: ASGIApp, output: StringIO
) -> None:
    with pytest.raises(RuntimeError):
        TestClient(application).get("/crash")
    assert len(http_events(output)) == 1
    assert structlog.contextvars.get_contextvars() == {}


@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("credentials", 401),
        ("token", 401),
        ("user", 404),
        ("username", 409),
        ("email", 409),
    ],
)
def test_domain_statuses(
    name: str, status: int, application: ASGIApp, output: StringIO
) -> None:
    response = TestClient(application).get(f"/domain/{name}")
    assert response.status_code == status
    assert http_events(output)[0]["level"] == "warning"
    assert not any("exception" in item for item in events(output))


def test_validation(application: ASGIApp, output: StringIO) -> None:
    assert TestClient(application).get("/validation").status_code == 422
    assert http_events(output)[0]["level"] == "warning"


def test_integrity_error_remains_domain_conflict(
    application: ASGIApp, output: StringIO
) -> None:
    session = AsyncMock()
    with patch("mini_jira.database.connection.SessionLocal") as factory:
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        response = TestClient(application).get("/expected-conflict")
    assert response.status_code == 409
    session.rollback.assert_awaited_once()
    assert not any("exception" in item for item in events(output))
    assert SECRET not in output.getvalue()


def test_cors_and_secret_input(application: ASGIApp, output: StringIO) -> None:
    client = TestClient(application)
    preflight = client.options(
        "/context",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ORIGIN
    assert not http_events(output)
    response = client.post(
        f"/context?token={SECRET}",
        headers={
            "Origin": ORIGIN,
            "Authorization": f"Bearer {SECRET}",
            "Cookie": f"refresh_token={SECRET}",
            "X-Request-ID": SECRET,
        },
        json={"password": SECRET, "username": SECRET, "email": SECRET},
    )
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]
    assert response.headers["X-Request-ID"] != SECRET
    assert SECRET not in output.getvalue()
    denied = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in denied.headers


def test_parent_context_restored(output: StringIO) -> None:
    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        assert structlog.contextvars.get_contextvars().keys() == {"request_id"}
        await Response()(scope, receive, send)

    structlog.contextvars.bind_contextvars(
        parent="preserved", request_id="outer"
    )
    TestClient(RequestLoggingMiddleware(downstream)).get("/")
    assert structlog.contextvars.get_contextvars() == {
        "parent": "preserved",
        "request_id": "outer",
    }
    assert not http_events(output)


def test_context_restored_in_same_task(
    application: ASGIApp, output: StringIO
) -> None:
    async def run() -> None:
        structlog.contextvars.bind_contextvars(
            parent="preserved", request_id="outer"
        )
        previous = structlog.contextvars.get_contextvars()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            for path in ["/health", "/crash", "/database-crash", "/context"]:
                if path == "/crash":
                    with pytest.raises(RuntimeError):
                        await client.get(path)
                else:
                    await client.get(path)
                assert structlog.contextvars.get_contextvars() == previous
        structlog.contextvars.clear_contextvars()

    asyncio.run(run())
    assert len(http_events(output)) == 4
    assert all(item["request_id"] != "outer" for item in events(output))
    assert all("parent" not in item for item in events(output))


@pytest.mark.parametrize("found", [False, True])
def test_login_failure_is_safe(found: bool, output: StringIO) -> None:
    repository = Mock()
    repository.get_by_username = AsyncMock(
        return_value=Mock(password_hash=SECRET) if found else None
    )
    credentials = UserCredentials(login="private-user", password=SECRET)
    with (
        patch("mini_jira.users.use_cases._hasher.verify", return_value=False),
        pytest.raises(InvalidCredentials),
    ):
        asyncio.run(LoginUserUseCase(repository).execute(credentials))
    (event,) = events(output)
    assert event["event"] == "auth.login.failed"
    assert event["reason"] == (
        "invalid_password" if found else "user_not_found"
    )
    assert event["level"] == "warning"
    assert SECRET not in output.getvalue()
    assert "private-user" not in output.getvalue()


def test_login_success(output: StringIO) -> None:
    user_id = uuid4()
    repository = Mock()
    repository.get_by_username = AsyncMock(
        return_value=Mock(id=user_id, password_hash=SECRET)
    )
    with patch("mini_jira.users.use_cases._hasher.verify", return_value=True):
        assert (
            asyncio.run(
                LoginUserUseCase(repository).execute(
                    UserCredentials(login="private-user", password=SECRET)
                )
            )
            == user_id
        )
    (event,) = events(output)
    assert event["event"] == "auth.login.succeeded"
    assert event["user_id"] == str(user_id)
    assert SECRET not in output.getvalue()


@pytest.mark.parametrize(
    ("operation", "event_name"),
    [
        ("register", "auth.register.succeeded"),
        ("refresh", "auth.refresh.rotated"),
        ("logout", "auth.logout.succeeded"),
        ("update", "users.profile.updated"),
        ("delete", "users.profile.deleted"),
    ],
)
@pytest.mark.parametrize("commit_fails", [False, True])
def test_business_success_requires_commit(
    operation: str, event_name: str, commit_fails: bool, output: StringIO
) -> None:
    user_id = uuid4()
    user = UserDTO.model_construct(
        id=user_id, username="private-user", email=SECRET
    )
    session = AsyncMock()

    async def commit() -> None:
        if commit_fails:
            raise SQLAlchemyError(SECRET)
        structlog.get_logger().info("test.committed")

    session.commit.side_effect = commit
    request = Request(
        {
            "type": "http",
            "headers": [(b"cookie", b"refresh_token=test-secret")],
        }
    )
    with (
        patch("mini_jira.auth.routes.RegisterUserUseCase") as register,
        patch("mini_jira.users.routes.UpdateUserProfileUseCase") as update,
        patch("mini_jira.users.routes.DeleteUserUseCase") as delete,
        patch(
            "mini_jira.auth.routes.validate_refresh_token",
            new_callable=AsyncMock,
            return_value=user_id,
        ),
        patch(
            "mini_jira.auth.routes.revoke_refresh_token",
            new_callable=AsyncMock,
        ),
        patch(
            "mini_jira.auth.routes.issue_token_pair",
            new_callable=AsyncMock,
            return_value=TokenPair(access=SECRET, refresh=SECRET),
        ),
    ):
        register.return_value.execute = AsyncMock(return_value=user)
        update.return_value.execute = AsyncMock(return_value=user)
        delete.return_value.execute = AsyncMock()
        if operation == "register":
            pending = register_user(
                Response(),
                UserRegister.model_construct(
                    username="private-user", email=SECRET, password=SECRET
                ),
                session,
            )
        elif operation == "refresh":
            pending = refresh_tokens(request, Response(), session)
        elif operation == "logout":
            pending = logout(request, Response(), session)
        elif operation == "update":
            pending = update_user(UserProfileUpdate(), user_id, session)
        else:
            pending = delete_user(user_id, session)
        if commit_fails:
            with pytest.raises(SQLAlchemyError):
                asyncio.run(pending)
            assert not events(output)
        else:
            asyncio.run(pending)
            assert [item["event"] for item in events(output)] == [
                "test.committed",
                event_name,
            ]
    assert SECRET not in output.getvalue()
    assert "private-user" not in output.getvalue()


def test_log_level_and_console_traceback(
    output: StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "log_level", "ERROR")
    monkeypatch.setattr(settings, "log_format", "console")
    configure_logging()
    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=output),
        cache_logger_on_first_use=False,
    )
    logger = structlog.get_logger()
    logger.warning("suppressed")
    try:
        raise RuntimeError(SECRET)
    except RuntimeError:
        logger.error("test.error", exc_info=True)
    text = output.getvalue()
    assert "suppressed" not in text
    assert "test.error" in text
    assert "Traceback" in text
    assert "RuntimeError" in text
    assert SECRET not in text
