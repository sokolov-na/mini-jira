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
def offline_email_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = Mock(spec=dns.resolver.Resolver)
    resolver.resolve.return_value = [
        Mock(preference=10, exchange="mx.example.org.")
    ]
    monkeypatch.setattr(dns.resolver, "get_default_resolver", lambda: resolver)
