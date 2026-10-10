# Changelog

Notable project changes are recorded here using Keep a Changelog categories.
No official release has been published; current functionality is unreleased.

## [Unreleased]

### Added

- User registration and login by username or email, with Argon2 password hashing
  and input validation/normalization.
- JWT access and refresh tokens with expiration, token-type checks, unique token
  IDs, hashed refresh-token persistence, rotation, and revocation.
- Authenticated profile read, username/email update, and account deletion.
- PostgreSQL persistence with async SQLAlchemy and Alembic migrations.
- Health endpoint, interactive API documentation, and OpenAPI schema.
- Environment-backed database, JWT, CORS, refresh-cookie, and logging settings
  with a safe example environment file.
- Structured stdout logging, per-request UUIDs, `X-Request-ID` response headers,
  HTTP severity mapping, and meaningful Auth/Users events.
- Central unexpected-error diagnostics with safe traceback rendering and
  generic HTTP 500 responses.
- Isolated logging, JWT, validation, and database-safety tests; PostgreSQL
  integration/API E2E test infrastructure with Alembic schema setup and
  transaction isolation and migration safety checks.
- pytest-cov tooling with branch coverage and missing-line reports, without a
  minimum coverage gate.
- Ruff, basedpyright, pre-commit, and uv dependency/lock-file tooling.

### Changed

- Passwords require at least eight characters, without mandatory uppercase
  letters or digits. Registration and profile updates enforce usernames of
  3–32 characters.
- Registration, profile updates and email login share normalization without
  DNS checks or automatic lowercasing of the ordinary email local part.

### Fixed

- A successful login revokes the previous refresh token supplied by its cookie.
- Refresh-cookie deletion uses the same configurable attributes as installation.
- Request IDs and allowed-origin CORS headers are preserved on unexpected 500
  responses.
- Database username/email length limits match ORM constraints, with a guarded
  migration that rejects oversized existing values instead of truncating them.

### Security

- Refresh cookies are HttpOnly and Secure by default. CORS origins must be
  explicit; wildcard origins are rejected when credentials are supported.
- Application logs omit request secrets, personal login values, SQL parameters,
  and potentially sensitive exception messages/local variables in application
  diagnostics. External component logs require separate review.
- Validation responses expose only `type`, `loc` and `msg`, with a stable
  `email_invalid` code and fixed message for invalid email values.
- JWT signing secrets must contain at least 32 characters.
