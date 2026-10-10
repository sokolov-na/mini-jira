from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from pwdlib import PasswordHash
from sqlalchemy import (
    URL,
    DateTime,
    Engine,
    String,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from alembic import command
from mini_jira.config import settings
from mini_jira.database.models import Base

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

PREVIOUS = "e0ee6d6e0e26"
REVISION = "9c2b4f7d1a60"


@pytest.fixture
def migration_environment(
    migrated_database: tuple[URL, str], monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Engine, Config]]:
    url, _ = migrated_database
    schema = "mini_jira_test_migration_" + uuid4().hex
    migration_url = url.update_query_dict(
        {"options": f"-csearch_path={schema}", "connect_timeout": "5"}
    )
    engine = create_engine(
        migration_url, poolclass=NullPool, hide_parameters=True
    )
    try:
        with engine.begin() as database:
            database.execute(text(f'CREATE SCHEMA "{schema}"'))
        monkeypatch.setattr(
            settings,
            "database_url",
            migration_url.render_as_string(hide_password=False).replace(
                "%", "%%"
            ),
        )
        yield (
            engine,
            Config(str(Path(__file__).resolve().parents[2] / "alembic.ini")),
        )
    finally:
        try:
            with engine.begin() as database:
                database.execute(
                    text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )
        finally:
            engine.dispose()


def test_fresh_migrations_match_all_orm_columns(
    migration_environment: tuple[Engine, Config],
) -> None:
    engine, config = migration_environment
    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {
        "alembic_version"
    }
    for table in Base.metadata.sorted_tables:
        reflected = {
            column["name"]: column
            for column in inspector.get_columns(table.name)
        }
        assert set(reflected) == set(table.columns.keys())
        for column in table.columns:
            actual = reflected[column.name]
            assert actual["nullable"] == column.nullable
            assert actual["default"] is None
            actual_type = actual["type"]
            assert isinstance(actual_type, type(column.type))
            if isinstance(column.type, String):
                assert isinstance(actual_type, String)
                assert actual_type.length == column.type.length
            if isinstance(column.type, DateTime):
                assert isinstance(actual_type, DateTime)
                assert actual_type.timezone == column.type.timezone
        assert inspector.get_pk_constraint(table.name)[
            "constrained_columns"
        ] == [column.name for column in table.primary_key]
        assert not [
            index
            for index in inspector.get_indexes(table.name)
            if not index.get("duplicates_constraint")
        ]
    assert {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("users")
    } == {("username",), ("email",)}
    assert {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("refresh_tokens")
    } == {("token_hash",)}
    foreign_keys = inspector.get_foreign_keys("refresh_tokens")
    assert len(foreign_keys) == 1
    assert foreign_keys[0]["constrained_columns"] == ["user_id"]
    assert foreign_keys[0]["referred_table"] == "users"
    assert foreign_keys[0]["referred_columns"] == ["id"]
    assert foreign_keys[0].get("options", {}).get("ondelete") == "CASCADE"
    with engine.connect() as database:
        context = MigrationContext.configure(
            database,
            opts={"compare_type": True, "compare_server_default": True},
        )
        assert compare_metadata(context, Base.metadata) == []
    command.check(config)


def test_upgrade_and_downgrade_preserve_users_and_refresh_tokens(
    migration_environment: tuple[Engine, Config],
) -> None:
    engine, config = migration_environment
    command.upgrade(config, PREVIOUS)
    user_id, token_id = uuid4(), uuid4()
    password_hash = PasswordHash.recommended().hash("migration-test-password")
    assert len(password_hash) > 64
    created_at = datetime.now(UTC)
    with engine.begin() as database:
        database.execute(
            text(
                "INSERT INTO users (id, username, email, password_hash) "
                "VALUES (:id, :username, :email, :password_hash)"
            ),
            {
                "id": user_id,
                "username": "u" * 32,
                "email": "e" * 244 + "@example.org",
                "password_hash": password_hash,
            },
        )
        database.execute(
            text(
                "INSERT INTO refresh_tokens "
                "(id, user_id, token_hash, revoked, expires_at, created_at) "
                "VALUES (:id, :user_id, :hash, false, :expires, :created)"
            ),
            {
                "id": token_id,
                "user_id": user_id,
                "hash": sha256(b"migration-test-token").hexdigest(),
                "expires": created_at + timedelta(days=1),
                "created": created_at,
            },
        )
        before_users = database.execute(text("SELECT * FROM users")).all()
        before_tokens = database.execute(
            text("SELECT * FROM refresh_tokens")
        ).all()
    for target in [REVISION, PREVIOUS, REVISION]:
        if target == PREVIOUS:
            command.downgrade(config, target)
        else:
            command.upgrade(config, target)
        with engine.connect() as database:
            assert (
                database.execute(text("SELECT * FROM users")).all()
                == before_users
            )
            assert (
                database.execute(text("SELECT * FROM refresh_tokens")).all()
                == before_tokens
            )
            assert (
                database.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
                == target
            )
        columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("users")
        }
        for name, length in [("username", 32), ("email", 256)]:
            column_type = columns[name]["type"]
            assert isinstance(column_type, String)
            assert column_type.length == (
                length if target == REVISION else None
            )


@pytest.mark.parametrize("field,length", [("username", 33), ("email", 257)])
def test_upgrade_refuses_oversized_data_without_changes(
    migration_environment: tuple[Engine, Config], field: str, length: int
) -> None:
    engine, config = migration_environment
    command.upgrade(config, PREVIOUS)
    values = {
        "id": uuid4(),
        "username": "test-user",
        "email": "test@example.org",
        "password_hash": "test-hash",
        field: "x" * length,
    }
    with engine.begin() as database:
        database.execute(
            text(
                "INSERT INTO users (id, username, email, password_hash) "
                "VALUES (:id, :username, :email, :password_hash)"
            ),
            values,
        )
        before = database.execute(text("SELECT * FROM users")).all()
    with pytest.raises(
        DBAPIError, match="Cannot constrain users: oversized username or email"
    ):
        command.upgrade(config, REVISION)
    with engine.connect() as database:
        assert database.execute(text("SELECT * FROM users")).all() == before
        assert (
            database.scalar(text("SELECT version_num FROM alembic_version"))
            == PREVIOUS
        )
    columns = inspect(engine).get_columns("users")
    for column in columns:
        if column["name"] in {"username", "email"}:
            column_type = column["type"]
            assert isinstance(column_type, String)
            assert column_type.length is None


@pytest.mark.parametrize("field,length", [("username", 33), ("email", 257)])
def test_new_schema_rejects_oversized_values(
    migration_environment: tuple[Engine, Config], field: str, length: int
) -> None:
    engine, config = migration_environment
    command.upgrade(config, "head")
    values = {
        "id": uuid4(),
        "username": "test-user",
        "email": "test@example.org",
        "password_hash": "test-hash",
        field: "x" * length,
    }
    with pytest.raises(DBAPIError), engine.begin() as database:
        database.execute(
            text(
                "INSERT INTO users (id, username, email, password_hash) "
                "VALUES (:id, :username, :email, :password_hash)"
            ),
            values,
        )
    with engine.connect() as database:
        assert database.scalar(text("SELECT count(*) FROM users")) == 0
