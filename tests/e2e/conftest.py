from collections.abc import AsyncIterator, Awaitable, Callable

import httpx2 as httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.auth.service import validate_access_token
from mini_jira.main import app
from tests.factories import PASSWORD, RegisteredUser, registration_data


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://api.example.org",
    ) as http_client:
        yield http_client


@pytest.fixture
def register(
    client: httpx.AsyncClient,
) -> Callable[[int], Awaitable[RegisteredUser]]:
    async def create(index: int = 1) -> RegisteredUser:
        data = registration_data(index)
        response = await client.post("/auth/register", json=data)
        assert response.status_code == 201, response.text
        access = str(response.json()["access_token"])
        refresh = client.cookies.get("refresh_token")
        assert refresh is not None
        return RegisteredUser(
            id=validate_access_token(access),
            username=data["username"],
            email=data["email"],
            password=PASSWORD,
            access=access,
            refresh=refresh,
        )

    return create
