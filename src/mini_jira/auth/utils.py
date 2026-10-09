from fastapi import Response

from mini_jira.config import settings


def set_refresh_token_cookie(
    response: Response,
    refresh_token: str,
) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        domain=settings.refresh_cookie_domain,
        path="/auth",
        max_age=7 * 24 * 60 * 60,
    )
