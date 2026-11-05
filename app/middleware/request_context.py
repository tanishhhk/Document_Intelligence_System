import logging
import time
import uuid

from app.logging_config import request_id_var

logger = logging.getLogger("app.request")

_ID_CHARACTERS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def _request_id(scope) -> str:
    supplied = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
    if 0 < len(supplied) <= 64 and set(supplied) <= _ID_CHARACTERS:
        return supplied
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """Give each request an ID, return it in X-Request-ID and log the outcome.

    The log line has the method, path (without the query string), status
    and duration. Headers and bodies are never logged.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope)
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_id(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message = {
                    **message,
                    "headers": [*message.get("headers", []), (b"x-request-id", request_id.encode())],
                }
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            logger.info(
                "Request handled.",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)
