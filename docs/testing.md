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

## Test levels and fixtures

`tests/unit` contains isolated logging/ASGI checks, JWT security, input validation,
and database safety checks. No PostgreSQL is required.
`tests/integration` covers real repositories and services.
`tests/e2e` exercises Auth/Users workflows through an async ASGI client.
Both database categories carry the `postgres` marker.

Root `tests/conftest.py` supplies safe application settings without reading local
`.env`, resets test logging configuration, and replaces external email DNS
resolution. Shared data and JWT factories live in `tests/factories.py`.
`tests/fixtures/database.py` owns database setup and sessions; specialized async
client and registration fixtures are in `tests/e2e/conftest.py`.

## PostgreSQL setup

Provision a dedicated database and test role. The role needs CREATE permission
on that database. Do not reuse a production or development database/role.

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://mini_jira_test:replace-with-test-password@localhost:5432/mini_jira_test"
uv run pytest -m postgres -ra
```

`TEST_DATABASE_URL` is read only from the process environment. The guard requires
`postgresql+psycopg`, explicit host/user, and a database name ending in `_test`.
URL query options are restricted to TLS settings so they cannot override the
guarded database, host, user, or search path. Missing configuration produces
explicit skips; an unsafe URL or unreachable configured database fails the run.

The fixtures upgrade a unique temporary schema to Alembic `head`, with a private
search path. Each test uses an outer transaction and savepoints, allowing real
application commits and rollbacks while test data is rolled back at teardown.
The schema is dropped at session teardown. Only generated test schemas are
removed; the database itself is not created or dropped by the test suite.

## Coverage and limitations

pytest-cov measures `mini_jira` production code, including branches. Tests,
migrations, and generated reports are outside the measured source. There is no
minimum percentage gate. Use missing lines to identify meaningful gaps rather
than adding tests solely to increase the percentage.

The current PostgreSQL integration/E2E suite has **not been run against real
PostgreSQL**, because no dedicated `TEST_DATABASE_URL` has been configured.
Passing isolated tests does not establish correctness of persisted registration,
refresh rotation/revocation, profile updates, or transaction rollback.

The per-test connection does not support concurrent HTTP transactions within one
DB test. API E2E tests use ASGITransport, not a real network server. DNS is replaced
for deterministic email validation; this does not verify real DNS availability.

A known security defect is tracked with `xfail(strict=True)`: FastAPI's default
registration validation response can echo the supplied password in the 422
`input` field. This is **not fixed**. An unexpected pass after a production fix
requires removing the marker. Production behavior is not modified by tests.
