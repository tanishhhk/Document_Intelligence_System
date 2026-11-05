import asyncio
import logging
import time
from collections import OrderedDict, deque

from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Authenticated requests also count toward their address, with this much
# headroom, so rotating many accounts from one address stays bounded.
SHARED_ADDRESS_MULTIPLIER = 10


class RateLimitMiddleware:
    """Basic per-process request limits keyed by caller and route group.

    Requests carrying a validly signed access token are counted per user, so
    users behind one shared address do not exhaust each other's limits. They
    also count toward their address with SHARED_ADDRESS_MULTIPLIER times the
    limit. Other requests, and all login and registration attempts, are
    counted per peer IP address.

    The peer address is the one the ASGI server reports. Behind a reverse
    proxy, run Uvicorn with --proxy-headers and --forwarded-allow-ips set to
    the proxy's address. This middleware never reads X-Forwarded-For itself.

    State lives in this process. Deployments with more than one worker or
    instance should enforce limits at a gateway or with a shared store such
    as Redis.
    """

    def __init__(self, app, settings, token_subject=None):
        self.app = app
        self.settings = settings
        self.window_seconds = 60
        self.max_tracked_keys = getattr(settings, "max_rate_limit_keys", 10_000)
        self.requests = OrderedDict()
        self.lock = asyncio.Lock()
        self.token_subject = token_subject

    def _bucket_for(self, method, path):
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "auth" and parts[1] in {"login", "register"}:
            return "auth", self.settings.auth_requests_per_minute
        if method == "POST" and path == "/documents/upload":
            return "upload", self.settings.upload_requests_per_minute
        if method == "POST" and path == "/chat/ask":
            return "chat", self.settings.chat_requests_per_minute
        if method == "POST" and len(parts) == 3 and parts[:2] == ["videos", "generate"]:
            return "video", self.settings.video_requests_per_minute
        return "general", self.settings.default_requests_per_minute

    def _limits_for(self, scope, bucket, limit):
        client = scope.get("client")
        address_key = ("ip", client[0] if client else "unknown", bucket)
        if bucket != "auth" and self.token_subject is not None:
            authorization = dict(scope.get("headers") or []).get(b"authorization", b"")
            scheme, _, token = authorization.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and token:
                user_id = self.token_subject(token.strip())
                if user_id:
                    return [
                        (("user", user_id, bucket), limit),
                        (address_key, limit * SHARED_ADDRESS_MULTIPLIER),
                    ]
        return [(address_key, limit)]

    def _history(self, key):
        history = self.requests.get(key)
        if history is None:
            # Evict the least recently used caller rather than refusing new
            # callers, so filling the map cannot lock everyone else out.
            while len(self.requests) >= self.max_tracked_keys:
                self.requests.popitem(last=False)
            history = deque()
            self.requests[key] = history
        self.requests.move_to_end(key)
        return history

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "/")
        bucket, limit = self._bucket_for(method, path)
        limits = self._limits_for(scope, bucket, limit)
        now = time.monotonic()
        retry_after = None

        async with self.lock:
            cutoff = now - self.window_seconds
            while self.requests:
                _oldest_key, oldest_history = next(iter(self.requests.items()))
                if not oldest_history or oldest_history[-1] <= cutoff:
                    self.requests.popitem(last=False)
                else:
                    break

            histories = []
            for key, key_limit in limits:
                history = self._history(key)
                while history and history[0] <= cutoff:
                    history.popleft()
                histories.append(history)
                if len(history) >= key_limit:
                    wait = max(1, int(self.window_seconds - (now - history[0])))
                    retry_after = max(retry_after or 0, wait)

            if retry_after is None:
                for history in histories:
                    history.append(now)

        if retry_after is not None:
            logger.warning("Rate limit exceeded.", extra={"bucket": bucket, "caller_type": limits[0][0][0]})
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Try again shortly."},
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
