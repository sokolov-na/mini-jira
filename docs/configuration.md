# Configuration

Run the application and Alembic from the `api` directory. Application settings
read `.env` relative to the working directory; environment variables take
precedence. Start with [the example](../.env.example), replace its credentials,
and generate a random JWT secret before running the API.
Never commit secrets or use example credentials for a public instance.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Required | PostgreSQL SQLAlchemy URL using `postgresql+psycopg` |
| `JWT_SECRET_KEY` | Required | Secret used to sign and verify HS256 JWTs |
| `CORS_ORIGINS` | `[]` | JSON array of exact permitted browser origins |
| `REFRESH_COOKIE_SECURE` | `true` | Restrict refresh cookie to HTTPS |
| `REFRESH_COOKIE_SAMESITE` | `lax` | `lax`, `strict`, or `none` |
| `REFRESH_COOKIE_DOMAIN` | Unset | Cookie domain; empty means host-only |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `LOG_FORMAT` | `console` | `console` or `json` |

## CORS and cookies

CORS origins include the scheme and port where needed, with no path or trailing
slash. Wildcards are rejected. An empty allowlist intentionally disables browser
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
