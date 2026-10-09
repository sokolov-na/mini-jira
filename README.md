# Application configuration

Copy `.env.example` to `.env` and set `DATABASE_URL` and a randomly generated
`JWT_SECRET_KEY` before starting the application. Environment variables override
values from `.env`. Never commit `.env` or use the example credentials publicly.

`CORS_ORIGINS` is a JSON array of exact frontend origins, including the scheme
and port when needed. Replace `https://app.example.com` with your frontend origin.
The default is an empty list; wildcards are rejected.

Keep `REFRESH_COOKIE_SECURE=true` for public HTTPS. For local HTTP only, set
`REFRESH_COOKIE_SECURE=false`. `REFRESH_COOKIE_SAMESITE` defaults to `lax` and
accepts `lax`, `strict`, or `none`; `none` requires Secure. Leave
`REFRESH_COOKIE_DOMAIN` empty for a host-only cookie, or set a domain when sharing
the cookie across hosts is required. HttpOnly, the `/auth` path, and the seven-day
lifetime are fixed. Logout uses the same cookie settings.

`.gitignore` and `.dockerignore` exclude `.env` and `.env.*`, while keeping
`.env.example` available. The Docker ignore rules apply when `api` is the build
context; a future build with a different context must exclude its env files too.
