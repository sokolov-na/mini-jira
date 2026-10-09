import logging
import sys
from traceback import walk_tb

import structlog
from structlog.types import ExcInfo

from mini_jira.config import settings


def format_safe_exception(exc_info: ExcInfo) -> str:
    exception_type, _, traceback = exc_info
    lines = ["Traceback (most recent call last):"]
    for frame, lineno in walk_tb(traceback):
        lines.append(
            f'  File "{frame.f_code.co_filename}", line {lineno}, '
            f"in {frame.f_code.co_name}"
        )
    lines.append(exception_type.__name__)
    return "\n".join(lines)


def configure_logging() -> None:
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(
            colors=sys.stdout.isatty(),
        )

    structlog.configure(
        processors=[
            *processors,
            structlog.processors.ExceptionRenderer(format_safe_exception),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level]
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
