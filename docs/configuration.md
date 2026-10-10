# Configuration

Run the application and Alembic from the `api` directory. Application settings
read `.env` relative to the working directory; environment variables take
precedence. Start with [the example](../.env.example), replace its credentials,
and generate a random JWT secret before running the API.
Never commit secrets or use example credentials for a public instance.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Required | PostgreSQL SQLAlchemy URL; use `postgresql+psycopg` for API and Alembic |
| `JWT_SECRET_KEY` | Required | HS256 signing secret, at least 32 characters; use a randomly generated value |
| `RESEND_API_KEY` | Required | Resend API key; keep secret |
| `RESEND_FROM_EMAIL` | Required | Sender address on a verified Resend domain |
| `PASSWORD_RESET_FRONTEND_URL` | Required | Trusted frontend base URL; reset links append `/reset-password?token=...` |
| `PASSWORD_RESET_EMAIL_SUBJECT` | `Mini Jira — Password Reset` | Nonempty subject for the plain-text reset email |
| `CORS_ORIGINS` | `[]` | JSON array of exact permitted browser origins |
| `REFRESH_COOKIE_SECURE` | `true` | Restrict refresh cookie to HTTPS |
| `REFRESH_COOKIE_SAMESITE` | `lax` | `lax`, `strict`, or `none` |
| `REFRESH_COOKIE_DOMAIN` | Unset | Cookie domain; empty means host-only |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `LOG_FORMAT` | `console` | `console` or `json` |

## CORS and cookies

CORS origins must match the browser Origin exactly: scheme, host and port where
needed, without a path or trailing slash. Settings reject wildcards but do not
validate origin syntax. An empty allowlist intentionally disables browser
cross-origin access and does not prevent direct API clients from using the API.
Credentials are enabled for allowed origins. `X-Request-ID` is exposed to
browser clients, including on handled and unhandled error responses.

Keep `REFRESH_COOKIE_SECURE=true` for public HTTPS. For local HTTP only, use
`false`. `SameSite=none` requires Secure. Enabling cross-site cookies should
include a separate review of the deployment's CSRF protections; CORS alone is
not CSRF protection.

Leave Domain empty unless cross-host sharing is needed. Refresh cookies always
use HttpOnly, the `/auth` path, and a seven-day lifetime. Logout uses the same
Domain, Path, Secure, HttpOnly, and SameSite settings to delete the cookie.

## Local files

`.gitignore` and `.dockerignore` exclude local environment files and generated
artifacts while preserving `.env.example`. Docker ignore rules apply to an
`api/` build context; other contexts need their own exclusions.

Test database configuration is separate and is not read from `.env`.
See [testing](testing.md).

## Password changes and reset delivery

An authenticated `PATCH /auth/password/update` returns an access token and
sets a new refresh cookie after commit. Password replacement, revocation of
all previous refresh sessions, invalidation of reset tokens and creation of the
current device's new session share one transaction. Existing access JWTs remain
valid until expiry (15 minutes). Reset confirmation revokes all refresh sessions
without automatically signing the user in.

Reset links use only `PASSWORD_RESET_FRONTEND_URL`, never request headers.
HTTPS is required outside localhost, `127.0.0.1` and `::1`; credentials, query
strings and fragments are rejected. A base path is supported. Configure the
frontend to handle `/reset-password` and keep tokens out of analytics and logs.

`POST /auth/password/reset` returns `202` with JSON `null` for known and unknown
users, including delivery failures. Database errors still use the standard safe `500`
response; no email is sent if commit fails. The token is committed before a single
Resend send attempt. A failed delivery leaves the new token active and previous
links invalidated; the user must request another email. There are no automatic
retries or delivery guarantees. Failures emit
`auth.password_reset.delivery_failed` with the exception type, without provider
messages, recipient addresses or reset links.

Response times can still reveal account existence because only known accounts
perform token storage and email delivery. Add request rate limits by IP and an
account-based reset cooldown to reduce enumeration and email abuse; these
controls are not implemented here. No artificial response delays are used.

The packaged [plain-text template](../src/mini_jira/auth/templates/password_reset.txt)
uses `$reset_url` and `$expires_minutes` placeholders. Expiry comes from the token
lifetime; change the template in the source and rebuild the package to deploy it.
The subject is configured separately; do not put the email body in `.env`.
