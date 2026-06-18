"""Rate limiting tests (per-user token bucket)."""

from __future__ import annotations

from app.services.rate_limiter import InMemoryRateLimiter


def test_bucket_blocks_after_capacity():
    limiter = InMemoryRateLimiter()
    # capacity = limit * burst = 3 * 1.0 = 3 tokens.
    allowed = 0
    blocked = 0
    for _ in range(6):
        result = limiter.check("k", limit=3, window_seconds=60, burst_multiplier=1.0)
        if result.allowed:
            allowed += 1
        else:
            blocked += 1
    assert allowed == 3
    assert blocked == 3


def test_retry_after_is_positive_when_blocked():
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        limiter.check("k", limit=3, window_seconds=60, burst_multiplier=1.0)
    result = limiter.check("k", limit=3, window_seconds=60, burst_multiplier=1.0)
    assert not result.allowed
    assert result.retry_after > 0


def test_endpoint_rate_limit_429(client, make_token):
    # Test env sets RATE_LIMIT_USER_REQUESTS=5, burst=1.0 -> 5 tokens.
    token = make_token(sub="rate-user", tenant_id="public")
    headers = {"Authorization": f"Bearer {token}"}

    statuses = [client.get("/api/v1/auth/whoami", headers=headers).status_code for _ in range(8)]
    assert statuses.count(200) == 5
    assert 429 in statuses

    blocked = next(
        client.get("/api/v1/auth/whoami", headers=headers) for _ in range(1)
    )
    if blocked.status_code == 429:
        assert "Retry-After" in blocked.headers
