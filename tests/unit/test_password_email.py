import json
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import HttpUrl, ValidationError
from resend.exceptions import ResendError

from mini_jira.auth.email import send_password_reset_email
from mini_jira.config import Settings, settings

pytestmark = pytest.mark.unit


async def test_email_uses_configured_sender_and_frontend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = AsyncMock(return_value={"id": "test-message"})
    monkeypatch.setattr("resend.Emails.send_async", sender)
    monkeypatch.setattr(
        settings,
        "password_reset_frontend_url",
        HttpUrl("https://trusted.example/app/"),
    )
    monkeypatch.setattr(settings, "resend_from_email", "sender@example.org")
    monkeypatch.setattr(
        settings, "password_reset_email_subject", "Configured subject"
    )
    await send_password_reset_email("recipient@example.org", "token+&?")
    sender.assert_awaited_once()
    payload = sender.call_args.args[0]
    assert payload["from"] == "Mini Jira <sender@example.org>"
    assert payload["to"] == ["recipient@example.org"]
    assert payload["subject"] == "Configured subject"
    assert (
        "https://trusted.example/app/reset-password?token=token%2B%26%3F"
        in payload["text"]
    )
    assert "10 minutes" in payload["text"]


@pytest.mark.parametrize("failure", ["provider", "network"])
async def test_delivery_failure_does_not_expose_provider_details(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "email@example.org secret-token secret-api-key https://example.org/reset?token=secret"
    error = (
        ResendError(500, "application_error", secret, secret)
        if failure == "provider"
        else TimeoutError(secret)
    )
    sender = AsyncMock(side_effect=error)
    monkeypatch.setattr("resend.Emails.send_async", sender)
    await send_password_reset_email("email@example.org", "secret-token")
    sender.assert_awaited_once()
    output = capsys.readouterr().out
    event = json.loads(output)
    assert event["event"] == "auth.password_reset.delivery_failed"
    assert event["level"] == "error"
    assert event["exception_type"] == type(error).__name__
    for sensitive in [
        "email@example.org",
        "secret-token",
        "secret-api-key",
        "https://example.org/reset",
    ]:
        assert sensitive not in output


async def test_template_failure_is_safe_and_does_not_send_email(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sender = AsyncMock()
    monkeypatch.setattr("resend.Emails.send_async", sender)
    monkeypatch.setattr(
        "mini_jira.auth.email.files",
        Mock(side_effect=FileNotFoundError("secret-file-path")),
    )
    await send_password_reset_email("private@example.org", "secret-token")
    sender.assert_not_awaited()
    output = capsys.readouterr().out
    event = json.loads(output)
    assert event["event"] == "auth.password_reset.delivery_failed"
    assert event["exception_type"] == "FileNotFoundError"
    for secret in ["secret-file-path", "secret-token", "private@example.org"]:
        assert secret not in output


@pytest.mark.parametrize(
    "url,valid",
    [
        ("https://app.example.org/base/", True),
        ("http://localhost:3000", True),
        ("http://127.0.0.1:3000", True),
        ("http://[::1]:3000", True),
        ("http://app.example.org", False),
        ("https://user:secret@app.example.org", False),
        ("https://app.example.org/?token=secret", False),
        ("https://app.example.org/#secret", False),
    ],
)
def test_reset_url_configuration(url: str, valid: bool) -> None:
    if valid:
        config = Settings.model_validate(
            settings.model_dump() | {"password_reset_frontend_url": url}
        )
        assert str(config.password_reset_frontend_url).startswith(
            url.rstrip("/")
        )
    else:
        with pytest.raises(ValidationError) as raised:
            Settings.model_validate(
                settings.model_dump() | {"password_reset_frontend_url": url}
            )
        assert raised.value.errors()[0]["type"] == "password_reset_url_invalid"
