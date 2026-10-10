# Mini Jira API

A learning backend project for Mini Jira. The current API implements
user registration, authentication, and account management.

## Features

- Registration and login by username or email.
- JWT access tokens and refresh tokens with rotation and revocation.
- Reading, updating, and deleting the authenticated user's profile.
- Authenticated password changes and one-time password reset links via Resend.
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
and JWT secret, configure the Resend key and sender and the trusted frontend
reset URL; never commit `.env` or use example secrets.

```powershell
Copy-Item .env.example .env
```

Database, JWT and reset-email settings are required. CORS origins, refresh-cookie
settings, email subject and logging are configurable. For local HTTP, set
`REFRESH_COOKIE_SECURE=false`; keep it enabled for public HTTPS.
An empty CORS allowlist is valid for an API without a browser frontend.
See [configuration](docs/configuration.md) for all variables.

## Run locally

Before upgrading an existing database, read [migration safety](docs/migrations.md).

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
| PATCH | `/auth/password/update` | Change password and replace refresh sessions with a new current session | Bearer access token |
| POST | `/auth/password/reset` | Request a reset email; returns 202 with JSON null | None |
| POST | `/auth/password/reset/confirm` | Consume a reset link and revoke refresh sessions without signing in | Reset token in body |
| GET | `/users/me` | Read own profile | Bearer access token |
| PATCH | `/users/me` | Update own username/email | Bearer access token |
| DELETE | `/users/me` | Delete own account; returns 204 | Bearer access token |

Token endpoints return `access_token` and `token_type: "bearer"`; refresh tokens
are delivered through HttpOnly cookies. Logout and reset confirmation keep their
200 response with JSON `null`; account deletion returns 204 without a body.

Usernames accept 3–32 Latin letters, digits and separating hyphens and are
lowercased. Passwords require at least eight characters, without mandatory
uppercase letters or digits. Email validation and normalization use EmailStr
without DNS checks; ordinary local-part case is preserved. Validation errors
return only `type`, `loc` and `msg`; invalid email uses `email_invalid`.

## Tests

```powershell
uv run pytest -m unit
uv run pytest -ra
```

Integration and E2E tests require `TEST_DATABASE_URL` pointing to a dedicated
PostgreSQL database ending in `_test`. Without it, these tests are explicitly
skipped. See [testing](docs/testing.md) for database setup, category and coverage
commands, isolation, and limitations.

## Documentation

- [Configuration](docs/configuration.md)
- [Testing](docs/testing.md)
- [Migrations](docs/migrations.md)
- [Logging](docs/logging.md)
- [Changelog](CHANGELOG.md)
