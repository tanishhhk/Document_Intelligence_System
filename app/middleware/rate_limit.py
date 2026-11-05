import asyncio
import time
from collections import OrderedDict, deque

from starlette.responses import JSONResponse


class RateLimitMiddleware:
    """Basic per-process request limits keyed by the peer IP and route group.

    Deployments with more than one worker or instance should use a shared rate
    limit store at the gateway or in Redis. This middleware does not trust
    caller-supplied X-Forwarded-For headers.
    """

    def __init__(self, app, settings):
        self.app = app
        self.settings = settings
        self.window_seconds = 60
        self.max_tracked_keys = 10_000
        self.requests = OrderedDict()
        self.lock = asyncio.Lock()

    def _bucket_for(self, method, path):
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "auth" and parts[1] in {"login", "register"}:
            return "auth", self.settings.auth_requests_per_minute
        if method == "POST" and path == "/documents/upload":
            return "upload", self.settings.upload_requests_per_minute
        if method == "POST" and path == "/chat/ask":
            return "chat", self.settings.chat_requests_per_minute
        return "general", self.settings.default_requests_per_minute

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        peer_ip = client[0] if client else "unknown"
        method = scope.get("method", "GET")
        path = scope.get("path", "/")
        bucket, limit = self._bucket_for(method, path)
        key = (peer_ip, bucket)
        now = time.monotonic()
        response = None

        async with self.lock:
            cutoff = now - self.window_seconds
            while self.requests:
                oldest_key, oldest_history = next(iter(self.requests.items()))
                if not oldest_history or oldest_history[-1] <= cutoff:
                    self.requests.popitem(last=False)
                else:
                    break

            history = self.requests.get(key)
            if history is None:
                if len(self.requests) >= self.max_tracked_keys:
                    response = JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests. Try again shortly."},
                        headers={"Retry-After": str(self.window_seconds)},
                    )
                else:
                    history = deque()
                    self.requests[key] = history

            if history is not None:
                while history and history[0] <= cutoff:
                    history.popleft()

                if len(history) >= limit:
                    retry_after = max(1, int(self.window_seconds - (now - history[0])))
                    response = JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests. Try again shortly."},
                        headers={"Retry-After": str(retry_after)},
                    )
                else:
                    history.append(now)
                    self.requests.move_to_end(key)

        if response is not None:
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
