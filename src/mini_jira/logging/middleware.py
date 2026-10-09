import time
from uuid import uuid4

import structlog
from fastapi.routing import APIRoute
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())

        previous_context = structlog.contextvars.get_contextvars()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        start_time = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            try:
                duration_ms = (time.perf_counter() - start_time) * 1000

                route = scope.get("route")
                if isinstance(route, APIRoute):
                    if status_code >= 500:
                        log = logger.error
                    elif status_code >= 400:
                        log = logger.warning
                    else:
                        log = logger.info

                    log(
                        "http.request",
                        method=scope["method"],
                        path=scope["path"],
                        status_code=status_code,
                        duration_ms=round(duration_ms, 2),
                    )
            finally:
                structlog.contextvars.clear_contextvars()
                structlog.contextvars.bind_contextvars(**previous_context)
