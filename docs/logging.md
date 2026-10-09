# Logging

Application logs go to stdout. Select `LOG_FORMAT=json` for structured output
or `console` for local use; `LOG_LEVEL` controls filtering. No application
log files or storage backend are configured.

## HTTP events and request IDs

One `http.request` event is emitted for each request matched to a FastAPI
`APIRoute`, including `/health`. Swagger, OpenAPI, and unknown URLs are omitted.
Events include `event`, `request_id`, `method`, `path`, `status_code`,
`duration_ms`, `level`, and `timestamp`. HTTP 1xx-3xx uses INFO, 4xx WARNING,
and 5xx ERROR, subject to the configured logging level.

The ASGI middleware creates a UUID for each HTTP request rather than trusting
an incoming request ID. It binds the ID through structlog contextvars,
returns it as `X-Request-ID`, and restores the previous context afterwards.
Request logging and CORS wrap the whole FastAPI application so that Starlette's
server-error responses also carry the ID and CORS headers for allowed origins.
The FastAPI object is `mini_jira.main:api`; the runnable ASGI application is
`mini_jira.main:app`.

## Business events

- `auth.login.succeeded` / `auth.login.failed`: credential verification in the
  login use case. Failures include a limited reason code, with no login value.
- `auth.refresh.revocation_requested`: pending revocation in the auth service;
  the surrounding transaction may still roll back.
- `auth.register.succeeded`, `auth.refresh.rotated`, `auth.logout.succeeded`:
  recorded after the corresponding transaction commits.
- `users.profile.updated` / `users.profile.deleted`: after a successful commit.
- `auth.token.rejected` / `users.operation.rejected`: expected domain refusals.

Events may include technical user IDs and limited reason codes. Bodies,
Authorization headers, passwords, usernames, email addresses, JWTs, refresh
cookies, and SQL parameters are not included in application events.

## Unexpected errors

Central handlers emit one ERROR diagnostic event: `database.unexpected_error`
for SQLAlchemy errors, or `application.unexpected_error` for other unexpected
exceptions. Diagnostics contain the component, exception type, request ID when
available, and traceback frames. Exception messages, source lines, locals,
chained exceptions, and SQL parameters are omitted to protect sensitive data.
Clients receive `500` with `{"detail": "Internal server error"}`.
The separate HTTP event records status 500 without repeating the traceback.

Expected domain errors retain their existing 401, 404, or 409 status;
validation remains 422. Known PostgreSQL uniqueness errors continue to be
translated to domain conflicts.

Starlette re-raises unhandled exceptions after constructing the 500 response.
This behavior is preserved and tested. Uvicorn can independently record another
traceback; application filtering does not apply to server logs. Review server
logging before relying on the same redaction guarantees outside structlog.
