from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx2 as httpx
import pytest
from resend.exceptions import ResendError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.service import issue_token_pair, save_password_reset_token
from mini_jira.auth.tokens import hash_token
from mini_jira.database.models import PasswordResetToken, RefreshToken, User
from tests.factories import RegisteredUser

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]
NEW_PASSWORD = "new-test-password"
RESET_TOKEN = "test-only-reset-token"


async def test_password_update_revokes_tokens_and_preserves_access(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    user = await register(1)
    extra = await issue_token_pair(db_session, user.id)
    await save_password_reset_token(db_session, user.id, RESET_TOKEN)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {user.access}"}
    wrong = await client.patch(
        "/auth/password/update",
        headers=headers,
        json={
            "current_password": "wrong-password",
            "new_password": NEW_PASSWORD,
        },
    )
    assert wrong.status_code == 400
    assert wrong.json() == {"detail": "Invalid password"}
    assert "set-cookie" not in wrong.headers
    db_session.expire_all()
    assert all(
        not token.revoked
        for token in await db_session.scalars(select(RefreshToken))
    )
    assert all(
        not token.consumed
        for token in await db_session.scalars(select(PasswordResetToken))
    )
    response = await client.patch(
        "/auth/password/update",
        headers=headers,
        json={"current_password": user.password, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    new_access = response.json()["access_token"]
    new_refresh = client.cookies.get("refresh_token")
    assert new_refresh is not None and new_refresh != user.refresh
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Max-Age=0" not in response.headers["set-cookie"]
    db_session.expire_all()
    tokens = (await db_session.scalars(select(RefreshToken))).all()
    assert len(tokens) == 3
    assert all(
        token.revoked == (token.token_hash != hash_token(new_refresh))
        for token in tokens
    )
    assert all(
        token.consumed
        for token in await db_session.scalars(select(PasswordResetToken))
    )
    assert (await client.get("/users/me", headers=headers)).status_code == 200
    assert (
        await client.get(
            "/users/me", headers={"Authorization": f"Bearer {new_access}"}
        )
    ).status_code == 200
    assert (await client.post("/auth/refresh")).status_code == 200
    client.cookies.clear()
    client.cookies.set("refresh_token", user.refresh)
    assert (await client.post("/auth/refresh")).status_code == 401
    client.cookies.set("refresh_token", extra.refresh)
    assert (await client.post("/auth/refresh")).status_code == 401
    assert (
        await client.post(
            "/auth/password/reset/confirm",
            json={
                "password_reset_token": RESET_TOKEN,
                "new_password": "another-password",
            },
        )
    ).status_code == 401
    assert (
        await client.post(
            "/auth/login",
            json={
                "login": user.username,
                "password": user.password,
            },
        )
    ).status_code == 401
    assert (
        await client.post(
            "/auth/login",
            json={
                "login": user.username,
                "password": NEW_PASSWORD,
            },
        )
    ).status_code == 200


@pytest.mark.parametrize("state", ["valid", "consumed", "expired", "missing"])
async def test_reset_confirmation_validity_and_replay(
    state: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
) -> None:
    user = await register(1)
    if state != "missing":
        await save_password_reset_token(db_session, user.id, RESET_TOKEN)
        await db_session.flush()
        token = await db_session.scalar(select(PasswordResetToken))
        assert token is not None
        token.consumed = state == "consumed"
        if state == "expired":
            token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.commit()
    payload = {
        "password_reset_token": RESET_TOKEN,
        "new_password": NEW_PASSWORD,
    }
    response = await client.post("/auth/password/reset/confirm", json=payload)
    assert response.status_code == (200 if state == "valid" else 401)
    assert "set-cookie" not in response.headers
    if state == "valid":
        assert response.json() is None
        db_session.expire_all()
        assert (
            await db_session.scalar(
                select(func.count()).select_from(RefreshToken)
            )
            == 1
        )
        assert all(
            token.revoked
            for token in await db_session.scalars(select(RefreshToken))
        )
    assert (
        await client.post("/auth/password/reset/confirm", json=payload)
    ).status_code == 401
    db_session.expire_all()
    stored = await db_session.get(User, user.id)
    assert stored is not None
    assert (
        await client.post(
            "/auth/login",
            json={
                "login": user.username,
                "password": NEW_PASSWORD
                if state == "valid"
                else user.password,
            },
        )
    ).status_code == 200
    if state == "valid":
        old = await db_session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_token(user.refresh)
            )
        )
        assert old is not None and old.revoked


@pytest.mark.parametrize("operation", ["update", "confirm"])
@pytest.mark.parametrize("failure", ["revocation", "commit"])
async def test_password_transaction_failure_rolls_back(
    operation: str,
    failure: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await register(1)
    await save_password_reset_token(db_session, user.id, RESET_TOKEN)
    await db_session.commit()
    stored = await db_session.get(User, user.id)
    assert stored is not None
    original_hash = stored.password_hash
    failed = AsyncMock(side_effect=SQLAlchemyError("test-only-failure"))
    if failure == "revocation":
        monkeypatch.setattr(
            "mini_jira.auth.service.revoke_all_refresh_tokens", failed
        )
    else:

        async def fail_commit(session: AsyncSession) -> None:
            await session.flush()
            raise SQLAlchemyError("test-only-failure")

        monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    if operation == "update":
        response = await client.patch(
            "/auth/password/update",
            headers={"Authorization": f"Bearer {user.access}"},
            json={
                "current_password": user.password,
                "new_password": NEW_PASSWORD,
            },
        )
    else:
        response = await client.post(
            "/auth/password/reset/confirm",
            json={
                "password_reset_token": RESET_TOKEN,
                "new_password": NEW_PASSWORD,
            },
        )
    assert response.status_code == 500
    assert "set-cookie" not in response.headers
    assert response.json() == {"detail": "Internal server error"}
    db_session.expire_all()
    stored = await db_session.get(User, user.id)
    token = await db_session.scalar(select(PasswordResetToken))
    refresh = await db_session.scalar(select(RefreshToken))
    assert stored is not None and stored.password_hash == original_hash
    assert token is not None and not token.consumed
    assert refresh is not None and not refresh.revoked
    assert (
        await db_session.scalar(select(func.count()).select_from(RefreshToken))
        == 1
    )


async def test_reset_issuance_invalidates_previous_token_without_real_email(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await register(1)
    sender = AsyncMock(return_value={"id": "test-email-id"})
    monkeypatch.setattr("resend.Emails.send_async", sender)
    response = await client.post(
        "/auth/password/reset", json={"login": user.username}
    )
    assert response.status_code == 202
    first = await db_session.scalar(select(PasswordResetToken))
    assert first is not None and not first.consumed
    first_id = first.id
    assert (
        await client.post("/auth/password/reset", json={"login": user.email})
    ).status_code == 202
    db_session.expire_all()
    tokens = (await db_session.scalars(select(PasswordResetToken))).all()
    assert len(tokens) == 2
    assert sum(not token.consumed for token in tokens) == 1
    assert next(token for token in tokens if token.id == first_id).consumed
    assert sender.await_count == 2

    assert (
        await client.post(
            "/auth/password/reset", json={"login": "missing-user"}
        )
    ).status_code == 202
    assert sender.await_count == 2


@pytest.mark.parametrize("delivery", ["success", "provider", "network"])
async def test_reset_response_is_independent_of_account_and_delivery(
    delivery: str,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await register(1)
    await save_password_reset_token(db_session, user.id, RESET_TOKEN)
    await db_session.commit()
    error = (
        ResendError(500, "application_error", "secret-provider-details", "")
        if delivery == "provider"
        else TimeoutError("secret-provider-details")
    )
    sender = AsyncMock(
        return_value={"id": "test-message"},
        side_effect=None if delivery == "success" else error,
    )
    monkeypatch.setattr("resend.Emails.send_async", sender)
    known = await client.post(
        "/auth/password/reset",
        json={"login": user.username},
        headers={
            "Host": "untrusted.example",
            "X-Forwarded-Host": "evil.example",
        },
    )
    unknown = await client.post(
        "/auth/password/reset", json={"login": "missing-user"}
    )
    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content == b"null"
    assert "set-cookie" not in known.headers
    sender.assert_awaited_once()
    text = sender.call_args.args[0]["text"]
    assert "https://frontend.example.com/reset-password?token=" in text
    assert "untrusted.example" not in text and "evil.example" not in text
    db_session.expire_all()
    tokens = (await db_session.scalars(select(PasswordResetToken))).all()
    assert len(tokens) == 2
    assert sum(not token.consumed for token in tokens) == 1
    assert next(
        t for t in tokens if t.token_hash == hash_token(RESET_TOKEN)
    ).consumed


async def test_reset_commit_failure_rolls_back_without_sending_email(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    register: Callable[[int], Awaitable[RegisteredUser]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await register(1)
    await save_password_reset_token(db_session, user.id, RESET_TOKEN)
    await db_session.commit()
    sender = AsyncMock()
    monkeypatch.setattr("resend.Emails.send_async", sender)

    async def fail_commit(session: AsyncSession) -> None:
        await session.flush()
        raise SQLAlchemyError("test-only-failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    response = await client.post(
        "/auth/password/reset", json={"login": user.username}
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    sender.assert_not_awaited()
    db_session.expire_all()
    tokens = (await db_session.scalars(select(PasswordResetToken))).all()
    assert len(tokens) == 1
    assert tokens[0].token_hash == hash_token(RESET_TOKEN)
    assert not tokens[0].consumed
