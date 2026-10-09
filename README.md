# Mini Jira API

A learning backend project for Mini Jira. The current API implements
user registration, authentication, and account management.

## Features

- Registration and login by username or email.
- JWT access tokens and refresh tokens with rotation and revocation.
- Reading, updating, and deleting the authenticated user's profile.
- Password hashing, input validation, and conflict handling.
- Structured stdout logs and request IDs.
- Isolated tests and PostgreSQL integration/API E2E test infrastructure.

## Tech stack

Python 3.14+, FastAPI, Pydantic, SQLAlchemy async, PostgreSQL, Alembic,
PyJWT, Argon2, and structlog. Development tools: uv, pytest, Ruff,
and basedpyright.

## Requirements

- Python 3.14 or newer and [uv](https://docs.astral.sh/uv/).
- PostgreSQL with an existing database and a role allowed to run migrations.

Run the following commands from the `api` repository directory.

## Configuration

Copy [.env.example](.env.example) to `.env`. Replace the database credentials
and JWT secret with your own values; never commit `.env` or use example secrets.

```powershell
Copy-Item .env.example .env
```

`DATABASE_URL` and `JWT_SECRET_KEY` are required. CORS origins, refresh-cookie
settings, and logging are configurable. For local HTTP, set
`REFRESH_COOKIE_SECURE=false`; keep it enabled for public HTTPS.
An empty CORS allowlist is valid for an API without a browser frontend.
See [configuration](docs/configuration.md) for all variables.

## Run locally

```powershell
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn mini_jira.main:app --reload
```

The API listens on `http://127.0.0.1:8000` by default. Interactive API docs
are available at `/docs`, with the schema at `/openapi.json`.

## API endpoints

| Method | Path | Description | Authentication |
| --- | --- | --- | --- |
| GET | `/health` | Service health | None |
| POST | `/auth/register` | Create an account and issue tokens | None |
| POST | `/auth/login` | Sign in and issue tokens | None |
| POST | `/auth/refresh` | Rotate the refresh token | Refresh cookie |
| POST | `/auth/logout` | Revoke refresh token and clear cookie | Cookie if present |
| GET | `/users/me` | Read own profile | Bearer access token |
| PATCH | `/users/me` | Update own username/email | Bearer access token |
| DELETE | `/users/me` | Delete own account; returns 204 | Bearer access token |

## Tests

```powershell
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m e2e
uv run pytest -ra
uv run pytest --cov=mini_jira --cov-branch --cov-report=term-missing -ra
```

Integration and E2E tests require `TEST_DATABASE_URL` pointing to a dedicated
PostgreSQL database ending in `_test`. Without it, these tests are explicitly
skipped. They have not yet been verified against real PostgreSQL.
See [testing](docs/testing.md) for setup, isolation, and known limitations.

## Documentation

- [Configuration](docs/configuration.md)
- [Testing](docs/testing.md)
- [Logging](docs/logging.md)
- [Changelog](CHANGELOG.md)
