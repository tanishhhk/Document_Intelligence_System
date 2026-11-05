from fastapi import HTTPException, status
from starlette.responses import JSONResponse

# Multipart framing (boundaries and part headers) around the uploaded file.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
DEFAULT_BODY_LIMIT_BYTES = 1024 * 1024


class BodySizeLimitMiddleware:
    """Reject request bodies above a size limit before they are buffered.

    Starlette spools a whole multipart body to a temporary file before the
    route handler runs, so the upload handler's own size check comes too
    late to protect the disk. This middleware checks Content-Length up front
    and counts streamed bytes for requests that do not declare a length.
    """

    def __init__(self, app, settings):
        self.app = app
        self.settings = settings

    def _limit_for(self, method: str, path: str) -> int:
        if method == "POST" and path == "/documents/upload":
            return self.settings.max_file_size + MULTIPART_OVERHEAD_BYTES
        return DEFAULT_BODY_LIMIT_BYTES

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self._limit_for(scope.get("method", "GET"), scope.get("path", "/"))
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None:
            if not declared.isdigit():
                await _reject(scope, receive, send, status.HTTP_400_BAD_REQUEST, "Invalid Content-Length.")
                return
            if int(declared) > limit:
                await _reject(scope, receive, send, status.HTTP_413_CONTENT_TOO_LARGE, "Request body is too large.")
                return

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Request body is too large.",
                    )
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_413_CONTENT_TOO_LARGE or response_started:
                raise
            await _reject(scope, receive, send, exc.status_code, exc.detail)


async def _reject(scope, receive, send, status_code, detail):
    response = JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers={"Connection": "close"},
    )
    await response(scope, receive, send)
