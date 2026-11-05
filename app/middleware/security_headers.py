"""Security headers on every response.

The API returns JSON and files, never pages to frame, so it denies framing and
content sniffing, sends no referrer, and asks browsers to keep to HTTPS. The
interactive docs at /docs load Swagger UI from a CDN, so only they skip the
strict content security policy.
"""
_COMMON = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"strict-transport-security", b"max-age=31536000"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
]
_STRICT_CSP = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = list(_COMMON)
        if not scope.get("path", "").startswith(_DOC_PATHS):
            headers.append(_STRICT_CSP)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _value in message.get("headers", [])}
                extra = [(name, value) for name, value in headers if name not in present]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, send_with_headers)
