from fastapi import Response

from mini_jira.auth.tokens import REFRESH_TOKEN_LIFETIME
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
        max_age=int(REFRESH_TOKEN_LIFETIME.total_seconds()),
    )


def delete_refresh_token_cookie(response: Response) -> None:
    response.delete_cookie(
        key="refresh_token",
        path="/auth",
        domain=settings.refresh_cookie_domain,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )
