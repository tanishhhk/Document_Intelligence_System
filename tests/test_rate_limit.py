import asyncio
from types import SimpleNamespace

from starlette.responses import PlainTextResponse

from app.middleware import rate_limit
from app.middleware.rate_limit import SHARED_ADDRESS_MULTIPLIER, RateLimitMiddleware

LIMITS = SimpleNamespace(
    auth_requests_per_minute=2,
    upload_requests_per_minute=2,
    chat_requests_per_minute=2,
    default_requests_per_minute=2,
    max_rate_limit_keys=100,
)


async def _ok(scope, receive, send):
    await PlainTextResponse("ok")(scope, receive, send)


def _limiter(**overrides):
    tokens = {"token-a": "user-a", "token-b": "user-b"}
    limiter = RateLimitMiddleware(_ok, LIMITS, token_subject=tokens.get)
    for name, value in overrides.items():
        setattr(limiter, name, value)
    return limiter


def _call(limiter, *, ip="198.51.100.1", path="/documents/list", method="GET", token=None, headers=()):
    raw_headers = list(headers)
    if token:
        raw_headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "client": (ip, 40000),
    }
    statuses = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    asyncio.run(limiter(scope, receive, send))
    return statuses[0]


def test_requests_within_the_limit_pass_and_excess_requests_are_rejected():
    limiter = _limiter()
    assert [_call(limiter) for _ in range(3)] == [200, 200, 429]


def test_different_addresses_have_separate_limits():
    limiter = _limiter()
    assert [_call(limiter, ip="198.51.100.1") for _ in range(2)] == [200, 200]
    assert _call(limiter, ip="198.51.100.2") == 200


def test_users_behind_one_address_have_separate_limits():
    limiter = _limiter()
    assert [_call(limiter, token="token-a") for _ in range(3)] == [200, 200, 429]
    assert _call(limiter, token="token-b") == 200


def test_rotating_accounts_from_one_address_stays_bounded():
    tokens = {f"token-{n}": f"user-{n}" for n in range(100)}
    limiter = RateLimitMiddleware(_ok, LIMITS, token_subject=tokens.get)
    allowed = sum(
        _call(limiter, token=f"token-{n}") == 200
        for n in range(100)
        for _ in range(LIMITS.default_requests_per_minute)
    )
    assert allowed == LIMITS.default_requests_per_minute * SHARED_ADDRESS_MULTIPLIER


def test_invalid_tokens_fall_back_to_the_address_limit():
    limiter = _limiter()
    statuses = [_call(limiter, token=f"forged-{n}") for n in range(3)]
    assert statuses == [200, 200, 429]


def test_login_attempts_are_limited_by_address_even_with_a_token():
    limiter = _limiter()
    statuses = [
        _call(limiter, path="/auth/login", method="POST", token=token)
        for token in ("token-a", "token-b", "token-a")
    ]
    assert statuses == [200, 200, 429]


def test_filling_the_tracking_map_does_not_lock_out_new_callers():
    limiter = _limiter(max_tracked_keys=100)
    for n in range(500):
        _call(limiter, ip=f"203.0.113.{n % 250}", path=f"/x{n // 250}")
    assert len(limiter.requests) <= 100
    assert _call(limiter, ip="192.0.2.50") == 200


def test_expired_entries_are_removed(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock["now"])
    limiter = _limiter()
    assert [_call(limiter) for _ in range(3)] == [200, 200, 429]

    clock["now"] += limiter.window_seconds + 1
    assert _call(limiter, ip="198.51.100.9") == 200
    assert ("ip", "198.51.100.1", "general") not in limiter.requests
    assert _call(limiter) == 200


def test_forwarded_for_headers_are_ignored():
    limiter = _limiter()
    for n in range(3):
        status = _call(limiter, headers=[(b"x-forwarded-for", f"192.0.2.{n}".encode())])
    assert status == 429


def test_rejections_report_when_to_retry():
    limiter = _limiter()
    headers = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            headers.update({k.decode(): v.decode() for k, v in message["headers"]})

    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("198.51.100.3", 1)}
    for _ in range(3):
        asyncio.run(limiter(scope, receive, send))
    assert 1 <= int(headers["retry-after"]) <= limiter.window_seconds
