import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import NamedTuple
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import Request, Response
from sqlalchemy import URL, delete, func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from mini_jira.auth.routes import (
    confirm_password_reset,
    login,
    refresh_tokens,
    reset_password,
    update_password,
)
from mini_jira.auth.service import (
    issue_token_pair,
    lock_user,
    save_password_reset_token,
)
from mini_jira.database.models import PasswordResetToken, RefreshToken, User
from mini_jira.exceptions import (
    InvalidCredentials,
    InvalidPassword,
    InvalidTokenError,
)
from mini_jira.users.repository.sqlalchemy import SQLAlchemyUserRepository
from mini_jira.users.schemas import (
    UserCredentials,
    UserPasswordReset,
    UserPasswordResetConfirm,
    UserPasswordUpdate,
    UserRegister,
)
from mini_jira.users.use_cases import RegisterUserUseCase
from tests.factories import PASSWORD, registration_data

pytestmark = [pytest.mark.integration, pytest.mark.postgres]
Operation = Callable[[AsyncSession], Awaitable[object]]


class AuthState(NamedTuple):
    sessions: async_sessionmaker[AsyncSession]
    user_id: UUID
    username: str
    refresh: str
    reset: str


@pytest_asyncio.fixture
async def auth_state(
    migrated_database: tuple[URL, str],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AuthState]:
    url, schema = migrated_database
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={
            "options": f"-csearch_path={schema} "
            "-clock_timeout=5000 -cstatement_timeout=10000",
            "connect_timeout": 5,
        },
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    username = "race-" + uuid4().hex[:16]
    user_id: UUID | None = None
    monkeypatch.setattr(
        "resend.Emails.send_async",
        AsyncMock(return_value={"id": "test-email"}),
    )
    try:
        async with sessions() as session:
            user = await RegisterUserUseCase(
                SQLAlchemyUserRepository(session)
            ).execute(
                UserRegister(
                    **(
                        registration_data()
                        | {
                            "username": username,
                            "email": username + "@example.org",
                        }
                    )
                )
            )
            user_id = user.id
            pair = await issue_token_pair(session, user.id)
            reset = "test-reset-" + uuid4().hex
            await save_password_reset_token(session, user.id, reset)
            await session.commit()
        yield AuthState(sessions, user_id, username, pair.refresh, reset)
    finally:
        try:
            if user_id is not None:
                async with sessions() as session:
                    await session.execute(
                        delete(User).where(User.id == user_id)
                    )
                    await session.commit()
        finally:
            await engine.dispose()


async def run_operation(
    state: AuthState,
    started: asyncio.Queue[int],
    operation: Operation,
) -> bool:
    async with state.sessions() as session:
        pid = await session.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(pid, int)
        started.put_nowait(pid)
        try:
            await operation(session)
        except InvalidTokenError, InvalidCredentials, InvalidPassword:
            await session.rollback()
            return False
        return True


async def wait_for_user_lock(
    state: AuthState, started: asyncio.Queue[int]
) -> None:
    async with asyncio.timeout(4):
        pid = await started.get()
        async with state.sessions() as monitor:
            while (
                await monitor.scalar(
                    text(
                        "SELECT wait_event_type FROM pg_stat_activity "
                        "WHERE pid = :pid"
                    ),
                    {"pid": pid},
                )
                != "Lock"
            ):
                await asyncio.sleep(0.01)


def cookie_request(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [
                (b"cookie", ("refresh_token=" + token).encode()),
            ],
        }
    )


async def rotate(state: AuthState, session: AsyncSession) -> object:
    return await refresh_tokens(
        cookie_request(state.refresh), Response(), session
    )


async def confirm(state: AuthState, session: AsyncSession) -> None:
    await confirm_password_reset(
        UserPasswordResetConfirm(
            password_reset_token=state.reset,
            new_password="new-race-password",
        ),
        session,
    )


async def issue_reset(state: AuthState, session: AsyncSession) -> None:
    await reset_password(UserPasswordReset(login=state.username), session)


async def change_password(state: AuthState, session: AsyncSession) -> object:
    return await update_password(
        UserPasswordUpdate(
            current_password=PASSWORD, new_password="new-race-password"
        ),
        Response(),
        state.user_id,
        session,
    )


@pytest.mark.parametrize("first", ["refresh", "update"])
async def test_password_change_preserves_only_its_new_session(
    auth_state: AuthState, first: str
) -> None:
    state = auth_state
    started: asyncio.Queue[int] = asyncio.Queue()

    async def blocked(session: AsyncSession) -> object:
        if first == "refresh":
            return await change_password(state, session)
        return await rotate(state, session)

    async with state.sessions() as owner, asyncio.TaskGroup() as group:
        await lock_user(owner, state.user_id)
        pending = group.create_task(run_operation(state, started, blocked))
        await wait_for_user_lock(state, started)
        if first == "refresh":
            await rotate(state, owner)
        else:
            await change_password(state, owner)
    assert pending.result() == (first == "refresh")
    async with state.sessions() as session:
        tokens = (
            await session.scalars(
                select(RefreshToken).where(
                    RefreshToken.user_id == state.user_id
                )
            )
        ).all()
        assert len(tokens) == (3 if first == "refresh" else 2)
        assert sum(not token.revoked for token in tokens) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PasswordResetToken)
                .where(
                    PasswordResetToken.user_id == state.user_id,
                    PasswordResetToken.consumed.is_(False),
                )
            )
            == 0
        )


@pytest.mark.parametrize(
    "operation", ["refresh", "confirm", "reset", "update"]
)
async def test_two_requests_are_serialized_by_user(
    auth_state: AuthState,
    operation: str,
) -> None:
    state = auth_state
    started: asyncio.Queue[int] = asyncio.Queue()

    async def execute(session: AsyncSession) -> object:
        if operation == "refresh":
            return await rotate(state, session)
        if operation == "confirm":
            return await confirm(state, session)
        if operation == "update":
            return await update_password(
                UserPasswordUpdate(
                    current_password=PASSWORD, new_password="new-race-password"
                ),
                Response(),
                state.user_id,
                session,
            )
        return await issue_reset(state, session)

    async with state.sessions() as owner, asyncio.TaskGroup() as group:
        await lock_user(owner, state.user_id)
        first = group.create_task(run_operation(state, started, execute))
        second = group.create_task(run_operation(state, started, execute))
        await wait_for_user_lock(state, started)
        await wait_for_user_lock(state, started)
        await owner.commit()
    assert sum([first.result(), second.result()]) == (
        2 if operation == "reset" else 1
    )
    async with state.sessions() as session:
        active_refresh = await session.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(
                RefreshToken.user_id == state.user_id,
                RefreshToken.revoked.is_(False),
            )
        )
        active_reset = await session.scalar(
            select(func.count())
            .select_from(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == state.user_id,
                PasswordResetToken.consumed.is_(False),
            )
        )
    if operation == "confirm":
        assert active_refresh == 0 and active_reset == 0
    elif operation in {"refresh", "update"}:
        assert active_refresh == 1
        if operation == "update":
            assert active_reset == 0
    else:
        assert active_reset == 1


@pytest.mark.parametrize("first", ["refresh", "confirm"])
async def test_refresh_and_reset_revoke_every_session(
    auth_state: AuthState,
    first: str,
) -> None:
    state = auth_state
    started: asyncio.Queue[int] = asyncio.Queue()

    async def blocked(session: AsyncSession) -> object:
        if first == "refresh":
            return await confirm(state, session)
        return await rotate(state, session)

    async with state.sessions() as owner, asyncio.TaskGroup() as group:
        await lock_user(owner, state.user_id)
        pending = group.create_task(run_operation(state, started, blocked))
        await wait_for_user_lock(state, started)
        if first == "refresh":
            await rotate(state, owner)
        else:
            await confirm(state, owner)
    assert pending.result() == (first == "refresh")
    async with state.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RefreshToken)
                .where(
                    RefreshToken.user_id == state.user_id,
                    RefreshToken.revoked.is_(False),
                )
            )
            == 0
        )


@pytest.mark.parametrize("first", ["reset", "confirm"])
async def test_reset_issuance_and_confirmation_have_consistent_order(
    auth_state: AuthState,
    first: str,
) -> None:
    state = auth_state
    started: asyncio.Queue[int] = asyncio.Queue()

    async def blocked(session: AsyncSession) -> object:
        if first == "reset":
            return await confirm(state, session)
        return await issue_reset(state, session)

    async with state.sessions() as owner, asyncio.TaskGroup() as group:
        await lock_user(owner, state.user_id)
        pending = group.create_task(run_operation(state, started, blocked))
        await wait_for_user_lock(state, started)
        if first == "reset":
            await issue_reset(state, owner)
        else:
            await confirm(state, owner)
    assert pending.result() == (first == "confirm")
    async with state.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PasswordResetToken)
                .where(
                    PasswordResetToken.user_id == state.user_id,
                    PasswordResetToken.consumed.is_(False),
                )
            )
            == 1
        )


async def test_login_rechecks_password_after_waiting_for_reset(
    auth_state: AuthState,
) -> None:
    state = auth_state
    started: asyncio.Queue[int] = asyncio.Queue()

    async def blocked(session: AsyncSession) -> object:
        return await login(
            UserCredentials(login=state.username, password=PASSWORD),
            Response(),
            Request({"type": "http", "headers": []}),
            session,
        )

    async with state.sessions() as owner, asyncio.TaskGroup() as group:
        await lock_user(owner, state.user_id)
        pending = group.create_task(run_operation(state, started, blocked))
        await wait_for_user_lock(state, started)
        await confirm(state, owner)
    assert not pending.result()


async def test_logins_with_other_users_cookies_do_not_deadlock(
    auth_state: AuthState,
) -> None:
    state = auth_state
    async with state.sessions() as session:
        user = await RegisterUserUseCase(
            SQLAlchemyUserRepository(session)
        ).execute(
            UserRegister(
                **(
                    registration_data(2)
                    | {
                        "username": state.username + "b",
                        "email": state.username + "b@example.org",
                    }
                )
            )
        )
        pair = await issue_token_pair(session, user.id)
        await session.commit()
    second_state = AuthState(
        state.sessions, user.id, user.username, pair.refresh, "unused"
    )
    started: asyncio.Queue[int] = asyncio.Queue()

    async def first_login(session: AsyncSession) -> object:
        return await login(
            UserCredentials(login=state.username, password=PASSWORD),
            Response(),
            cookie_request(second_state.refresh),
            session,
        )

    async def second_login(session: AsyncSession) -> object:
        return await login(
            UserCredentials(login=second_state.username, password=PASSWORD),
            Response(),
            cookie_request(state.refresh),
            session,
        )

    try:
        async with state.sessions() as owner, asyncio.TaskGroup() as group:
            for user_id in sorted(
                [state.user_id, second_state.user_id], key=str
            ):
                await lock_user(owner, user_id)
            first = group.create_task(
                run_operation(state, started, first_login)
            )
            second = group.create_task(
                run_operation(second_state, started, second_login)
            )
            await wait_for_user_lock(state, started)
            await wait_for_user_lock(state, started)
            await owner.commit()
        assert first.result() and second.result()
        async with state.sessions() as session:
            for user_id in [state.user_id, second_state.user_id]:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(RefreshToken)
                        .where(
                            RefreshToken.user_id == user_id,
                            RefreshToken.revoked.is_(False),
                        )
                    )
                    == 1
                )
    finally:
        async with state.sessions() as session:
            await session.execute(
                delete(User).where(User.id == second_state.user_id)
            )
            await session.commit()
