from fastapi import Response


def set_refresh_token_cookie(
    response: Response,
    refresh_token: str,
) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # TEMPORARY
        samesite="lax",
        path="/auth",
        max_age=7 * 24 * 60 * 60,
    )
