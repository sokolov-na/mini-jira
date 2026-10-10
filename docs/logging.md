# Logging

Application logs go to stdout. `LOG_FORMAT` selects `console` (default) or `json`;
`LOG_LEVEL` controls filtering. No application log files or storage backend are
configured. See [configuration](configuration.md) for allowed values.

## HTTP events and request IDs

Each HTTP request reaching the request middleware receives a generated UUID in
`X-Request-ID`; incoming IDs are not trusted. The ID is available to application
logs during the request, and the previous context is restored afterwards.
CORS preflight requests are handled before this middleware.

One `http.request` event is emitted for a registered API route, including
`/health`. `/docs`, `/openapi.json` and unknown URLs are omitted. Fields are
`event`, `request_id`, `method`, `path`, `status_code`, `duration_ms`, `level`
and `timestamp`. Statuses 1xx–3xx use INFO, 4xx WARNING and 5xx ERROR, subject to
`LOG_LEVEL`.

Request logging and CORS wrap FastAPI's error handling, preserving request IDs
and allowed-origin CORS headers on unexpected 500 responses. Browser clients
can read `X-Request-ID` for allowed origins.

## Business events

- `auth.login.succeeded` / `auth.login.failed`: credential verification, with
  limited reason codes for failures.
- `auth.refresh.revocation_requested`: revocation requested inside a transaction
  that may still roll back.
- `auth.register.succeeded`, `auth.refresh.rotated`, `auth.logout.succeeded`,
  `users.profile.updated`, `users.profile.deleted`, `users.password.updated`: recorded after commit.
- `auth.password_update.failed` / `auth.password_reset.failed`: expected refusals
  with limited reason codes.
- `auth.password_reset.delivery_failed`: email preparation/provider failure; logs
  the component and exception type without recipient, link or provider message.
- `auth.token.rejected` / `users.operation.rejected`: expected domain refusals.

Application events use technical IDs and reason codes rather than request bodies,
Authorization headers, passwords, usernames, email addresses, JWTs or cookies.
This is a convention of the current event producers, not a general redaction
filter for arbitrary fields.

## Unexpected errors

Central handlers emit ERROR diagnostics: `database.unexpected_error` for
unexpected SQLAlchemy errors and `application.unexpected_error` for other
exceptions. Diagnostics contain the component, exception type, request ID when
available and traceback frames. The application traceback renderer omits
exception messages, source lines, locals, chained exceptions and SQL parameters.
Clients receive `500` with `{"detail": "Internal server error"}`. The HTTP event
records the status separately without repeating the traceback.

Expected domain errors keep their 401, 404 or 409 status; an incorrect current
password returns 400. Validation returns 422.
Known database uniqueness errors are translated to domain conflicts.

Starlette re-raises unhandled exceptions after sending its 500 response. Uvicorn
may therefore emit an additional traceback. Application formatting does not
control Uvicorn, database-driver, proxy or other external logs; configure and
review those separately for sensitive data.
