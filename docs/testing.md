# Testing

Run commands from `api` after `uv sync --group dev`.

```powershell
uv run pytest -ra
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m e2e
uv run pytest -m postgres -ra
uv run pytest --cov=mini_jira --cov-branch --cov-report=term-missing -ra
```

Coverage measures production code, including branches, excluding tests and
migrations. There is no minimum percentage gate; use missing lines to find
meaningful gaps.

## Levels and fixtures

- `tests/unit`: isolated validation, authentication, logging and safety checks;
  no PostgreSQL required.
- `tests/integration`: repositories, services and migrations against PostgreSQL.
- `tests/e2e`: Auth/Users workflows through an ASGI client and PostgreSQL.

Database tests also carry the `postgres` marker. Root `tests/conftest.py` supplies
isolated settings without reading `.env` and resets logging. Shared factories
are in `tests/factories.py`, database fixtures in `tests/fixtures/database.py`,
and HTTP client/registration fixtures in `tests/e2e/conftest.py`.

## Safe PostgreSQL setup

Use a dedicated database and test role, never a development or production
connection. The role needs permission to create schemas and run migrations.
An administrator can provision them in `psql` after checking that neither name
already exists:

```sql
CREATE ROLE mini_jira_test LOGIN
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
\password mini_jira_test
CREATE DATABASE mini_jira_test OWNER mini_jira_test;
```

Database ownership supplies the required privileges. Enter the test password
interactively; do not commit it. For an existing test role, use
`\password mini_jira_test` to change its password. URL-encode special characters
when constructing the connection URL.

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://mini_jira_test:replace-with-test-password@localhost:5432/mini_jira_test"
uv run pytest -m postgres -ra
Remove-Item Env:TEST_DATABASE_URL
```

`TEST_DATABASE_URL` comes only from the process environment, not `.env`.
The guard requires `postgresql+psycopg`, an explicit host/user and a database name
ending in `_test`. Only supported TLS query options are permitted. This naming
check is a safeguard, not proof that the database is disposable: verify the
actual connection before running tests. Missing configuration skips database
tests; an unsafe URL or unreachable configured database fails the run.

Fixtures migrate a unique temporary schema to `head` with a private search path.
Repository/API tests use an outer transaction and savepoints so application
commits and rollbacks do not persist test data. Migration tests use separate
schemas per case to allow committed DDL. Teardown removes only generated test
schemas; it does not drop the database.

## Limitations

- A database test shares one connection and cannot run concurrent HTTP
  transactions. Logging concurrency tests are isolated from PostgreSQL.
- E2E tests use ASGITransport, not a network server.
- Email DNS resolution is replaced or prohibited for deterministic tests.
- On Windows, the asyncio fixture uses SelectorEventLoop because Psycopg async
  connections do not support ProactorEventLoop.
