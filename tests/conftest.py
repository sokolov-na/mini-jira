import asyncio
import importlib
import os
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import dns.resolver
import pytest
import resend
import structlog

pytest_plugins = ["tests.fixtures.database"]


def pytest_asyncio_loop_factories() -> dict[
    str, Callable[[], asyncio.AbstractEventLoop]
]:
    factory = (
        asyncio.SelectorEventLoop
        if sys.platform == "win32"
        else asyncio.new_event_loop
    )
    return {"database_compatible": factory}


os.environ.update(
    DATABASE_URL="postgresql+psycopg://invalid:invalid@127.0.0.1:1/unused_test",
    JWT_SECRET_KEY="test-only-key-never-use-in-production",
    RESEND_API_KEY="test-only-no-network",
    RESEND_FROM_EMAIL="noreply@example.org",
    PASSWORD_RESET_FRONTEND_URL="https://frontend.example.com",
    PASSWORD_RESET_EMAIL_SUBJECT="Mini Jira — Password Reset",
    CORS_ORIGINS='["https://frontend.example.com"]',
    REFRESH_COOKIE_SECURE="true",
    REFRESH_COOKIE_SAMESITE="lax",
    REFRESH_COOKIE_DOMAIN="",
    LOG_LEVEL="INFO",
    LOG_FORMAT="json",
)

previous_directory = Path.cwd()
with TemporaryDirectory() as isolated_directory:
    try:
        os.chdir(isolated_directory)
        importlib.import_module("mini_jira.config")
    finally:
        os.chdir(previous_directory)


@pytest.fixture(autouse=True)
def uncached_test_loggers() -> None:
    from mini_jira.logging.config import configure_logging

    configure_logging()
    structlog.configure(cache_logger_on_first_use=False)


@pytest.fixture(autouse=True)
def disable_email_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    sender = Mock(side_effect=AssertionError("Unexpected email delivery"))
    monkeypatch.setattr(resend.Emails, "send_async", sender)


@pytest.fixture(autouse=True)
def offline_email_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = Mock(spec=dns.resolver.Resolver)
    resolver.resolve.return_value = [
        Mock(preference=10, exchange="mx.example.org.")
    ]
    monkeypatch.setattr(dns.resolver, "get_default_resolver", lambda: resolver)
