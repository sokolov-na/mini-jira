from importlib.resources import files
from string import Template
from urllib.parse import urlencode

import resend
import structlog

from mini_jira.auth.tokens import PASSWORD_RESET_TOKEN_LIFETIME
from mini_jira.config import settings

logger = structlog.get_logger(__name__)


def _render_password_reset_email(token: str) -> str:
    reset_url = (
        str(settings.password_reset_frontend_url).rstrip("/")
        + "/reset-password?"
        + urlencode({"token": token})
    )
    template = (
        files("mini_jira")
        .joinpath("auth", "templates", "password_reset.txt")
        .read_text(encoding="utf-8")
    )
    return Template(template).substitute(
        reset_url=reset_url,
        expires_minutes=int(
            PASSWORD_RESET_TOKEN_LIFETIME.total_seconds() / 60
        ),
    )


async def send_password_reset_email(email: str, token: str) -> None:
    resend.api_key = settings.resend_api_key
    try:
        await resend.Emails.send_async(
            {
                "from": f"Mini Jira <{settings.resend_from_email}>",
                "to": [email],
                "subject": settings.password_reset_email_subject,
                "text": _render_password_reset_email(token),
            }
        )
    except Exception as exc:
        logger.error(
            "auth.password_reset.delivery_failed",
            component="password_reset_email",
            exception_type=type(exc).__name__,
        )
