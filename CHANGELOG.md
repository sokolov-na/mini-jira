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
- PostgreSQL persistence with async SQLAlchemy, domain repository/use-case
  boundaries, and Alembic migrations for users and refresh tokens.
- Health endpoint, interactive API documentation, and OpenAPI schema.
- Environment-backed database, JWT, CORS, refresh-cookie, and logging settings
  with a safe example environment file.
- Structured stdout logging, per-request UUIDs, `X-Request-ID` response headers,
  HTTP severity mapping, and meaningful Auth/Users events.
- Central unexpected-error diagnostics with safe traceback rendering and
  generic HTTP 500 responses.
- Isolated logging, JWT, validation, and database-safety tests; PostgreSQL
  integration/API E2E test infrastructure with Alembic schema setup and
  transaction isolation. PostgreSQL scenarios await their first real DB run.
- pytest-cov tooling with branch coverage and missing-line reports, without a
  minimum coverage gate.
- Ruff, basedpyright, pre-commit, and uv dependency/lock-file tooling.

### Changed

- User updates and deletes operate on domain users through the repository layer.
  Profile updates return the updated profile; deletion returns 204 No Content.
- Known database uniqueness errors map to 409 domain conflicts. Authentication,
  missing-user, and validation errors retain their 401, 404, and 422 responses.
- Logging and CORS wrap the full ASGI application, preserving request IDs and
  allowed-origin CORS headers on unexpected HTTP 500 responses.

### Fixed

- A successful login revokes the previous refresh token supplied by its cookie.
- Refresh-cookie deletion uses the same configurable attributes as installation.

### Security

- Refresh cookies are HttpOnly and Secure by default. CORS origins must be
  explicit; wildcard origins are rejected when credentials are supported.
- Application logs omit request secrets, personal login values, SQL parameters,
  and potentially sensitive exception messages/local variables.
- The default 422 registration response can still echo password input. This
  known issue is recorded by a strict expected-failure test and remains unfixed.
