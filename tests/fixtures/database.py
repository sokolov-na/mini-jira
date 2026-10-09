import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from alembic import command
from mini_jira.config import settings
from mini_jira.database import connection


def validate_test_database_url(value: str) -> URL:
    try:
        url = make_url(value)
    except ArgumentError as exc:
        raise ValueError("Invalid TEST_DATABASE_URL") from exc
    if (
        url.drivername != "postgresql+psycopg"
        or not url.database
        or not url.database.endswith("_test")
        or not url.host
        or not url.username
        or set(url.query)
        - {"sslmode", "sslrootcert", "sslcert", "sslkey", "channel_binding"}
    ):
        raise ValueError(
            "TEST_DATABASE_URL must use postgresql+psycopg and a dedicated "
            "database ending in _test, with explicit host and user"
        )
    return url


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[tuple[URL, str]]:
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("PostgreSQL tests require a dedicated TEST_DATABASE_URL")
    try:
        url = validate_test_database_url(value)
    except ValueError:
        pytest.fail(
            "Unsafe TEST_DATABASE_URL; use a dedicated *_test database",
            pytrace=False,
        )
    schema = "mini_jira_test_" + uuid4().hex
    engine = create_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.begin() as database:
            assert (
                database.scalar(text("SELECT current_database()"))
                == url.database
            )
            database.execute(text(f'CREATE SCHEMA "{schema}"'))
    except SQLAlchemyError:
        engine.dispose()
        pytest.fail(
            "Test PostgreSQL unavailable or schema creation denied",
            pytrace=False,
        )
    original_url = settings.database_url
    root = Path(__file__).resolve().parents[2]
    migration_url = url.update_query_dict(
        {
            "options": f"-csearch_path={schema}",
            "connect_timeout": "5",
        }
    )
    try:
        settings.database_url = migration_url.render_as_string(
            hide_password=False
        ).replace("%", "%%")
        config = Config(str(root / "alembic.ini"))
        command.upgrade(config, "head")
        settings.database_url = original_url
        yield url, schema
    finally:
        settings.database_url = original_url
        try:
            with engine.begin() as database:
                database.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    migrated_database: tuple[URL, str], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncSession]:
    url, schema = migrated_database
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={
            "options": f"-csearch_path={schema}",
            "connect_timeout": 5,
        },
    )
    try:
        async with engine.connect() as database:
            transaction = await database.begin()
            factory = async_sessionmaker(
                database,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            monkeypatch.setattr(connection, "SessionLocal", factory)
            try:
                async with factory() as session:
                    yield session
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
