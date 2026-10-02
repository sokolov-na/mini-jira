# Changelog

This changelog describes the project's development history in chronological order. The repository does not use release tags, so the entries are grouped by major development stages and the branches that introduced them.

## [Unreleased]

### Authentication flow

Development on `feat/users-auth`, later rebuilt on `feat/users-auth-restore`, extends the user-management foundation with a JWT-based authentication flow:

- Added JWT configuration and the `PyJWT` dependency.
- Added access and refresh token creation, validation, expiration checks, token type checks, token identifiers, and hashed refresh-token storage.
- Added the `refresh_tokens` database model and its Alembic migration, including user foreign-key cascading and revocation state.
- Added user registration under `/auth/register`.
- Added login by email or username under `/auth/login`.
- Added refresh-token rotation under `/auth/refresh`.
- Added refresh-token revocation and cookie cleanup under `/auth/logout`.
- Added refresh-token cookie handling and normalized registration email addresses.
- Added invalid-credentials and invalid-token HTTP error handling.
- Moved user creation responsibilities from the users router into the auth module.
- Added transaction rollback and integrity-error translation at the database session boundary.
- The initial auth branch was merged into `main` and subsequently reverted while the integration was being corrected.
- Recreated the complete auth change set on top of the latest `main` in `feat/users-auth-restore` for reintegration.

## 2026-09-29 — User management

### User CRUD and password protection

The `feat/users` branch added the first application-level user workflow on top of the database foundation:

- Added user create, read, update, and delete endpoints under `/users`.
- Added Pydantic schemas for user input, updates, and response DTOs.
- Added username and password validation rules.
- Added password hashing with `pwdlib` and Argon2 support.
- Added PostgreSQL integrity-error translation for duplicate usernames and emails.
- Added HTTP handlers for duplicate users and missing users.
- Converted the database layer and request handlers to SQLAlchemy's async engine and sessions.

## 2026-09-22 — Database foundation

### Database integration and migrations

The `feat/database` branch introduced persistent storage and was merged into `main` by pull request #2.

- Added environment-backed application settings with `DATABASE_URL` support.
- Added SQLAlchemy models and database connection management.
- Added Alembic configuration and migration infrastructure.
- Added the initial `users` table migration with UUID primary keys and unique username/email constraints.
- Added a follow-up migration renaming the user password column to `password_hash`.

## 2026-09-18 — Health endpoint and tooling

### Development baseline

The `feat/health-endpoint` branch was merged into `main` by pull request #1.

- Added the `/health` endpoint returning the service status.
- Added project development tooling and pre-commit checks.
- Updated dependency and lock-file configuration for the development setup.

## 2026-09-17 — Project initialization

### Initial project setup

- Initialized the Python project and package structure.
- Added project metadata, Python version configuration, dependency management, and the initial lock file.
- Added the initial README and Git ignore configuration.
