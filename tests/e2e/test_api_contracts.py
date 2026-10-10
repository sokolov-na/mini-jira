from unittest.mock import AsyncMock

import httpx2 as httpx
import pytest

from mini_jira.auth.schemas import AccessTokenResponse
from mini_jira.users.schemas import UserDTO
from tests.factories import PASSWORD, registration_data

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]


async def test_response_contracts_through_account_lifecycle(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = registration_data()
    assert (await client.get("/health")).json() == {"status": "ok"}
    registered = await client.post("/auth/register", json=data)
    assert registered.status_code == 201
    AccessTokenResponse.model_validate(registered.json())
    logged_in = await client.post(
        "/auth/login", json={"login": data["username"], "password": PASSWORD}
    )
    assert logged_in.status_code == 200
    AccessTokenResponse.model_validate(logged_in.json())
    rotated = await client.post("/auth/refresh")
    assert rotated.status_code == 200
    token = AccessTokenResponse.model_validate(rotated.json())
    headers = {"Authorization": f"Bearer {token.access_token}"}
    profile = await client.get("/users/me", headers=headers)
    assert profile.status_code == 200
    user = UserDTO.model_validate(profile.json())
    updated = await client.patch("/users/me", headers=headers, json={})
    assert updated.status_code == 200
    assert UserDTO.model_validate(updated.json()) == user
    changed = await client.patch(
        "/auth/password/update",
        headers=headers,
        json={
            "current_password": PASSWORD,
            "new_password": "new-test-password",
        },
    )
    assert changed.status_code == 200
    AccessTokenResponse.model_validate(changed.json())
    for response in [registered, logged_in, rotated, changed]:
        assert set(response.json()) == {"access_token", "token_type"}
        assert response.json()["token_type"] == "bearer"
    monkeypatch.setattr("resend.Emails.send_async", AsyncMock())
    reset = await client.post(
        "/auth/password/reset", json={"login": user.username}
    )
    assert reset.status_code == 202 and reset.content == b"null"
    logged_out = await client.post("/auth/logout")
    assert logged_out.status_code == 200 and logged_out.content == b"null"
    deleted = await client.delete("/users/me", headers=headers)
    assert deleted.status_code == 204 and deleted.content == b""
