"""Rate-limit-aware backoff in the model cascade.

Every model in MODEL_PRIORITY shares one OpenRouter account, so an account-level 429
throttles the whole cascade at once. Without spacing, the 7-model cascade plus the
caller's retries fire within seconds and all land inside the same rate-limit window —
which is how documents were silently dropped. On a 429 we now back off (honoring
Retry-After when given) so attempts straddle the window instead of bunching up.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.llm import (
    _RATE_LIMIT_MAX_DELAY,
    MODEL_PRIORITY,
    Model,
    _completion_with_fallback_impl,
    _is_rate_limited,
    _rate_limit_delay,
)

# Resolve models without needing OPENROUTER_API_KEY in the test env (CI has no key).
_fake_model = lambda _name: Model(model="test-model", api_key="test-key")  # noqa: E731


class _RateLimited(Exception):
    status_code = 429
    response: object = None  # set per-test to simulate a Retry-After header


def test_is_rate_limited_detects_429() -> None:
    assert _is_rate_limited(_RateLimited("slow down"))
    assert _is_rate_limited(Exception("HTTP 429: too many requests"))

    class _RateLimitError(Exception):
        pass

    assert _is_rate_limited(_RateLimitError("x"))
    assert _is_rate_limited(Exception("rate limit exceeded"))
    # Unrelated failures are not treated as rate limits — including "429" inside a
    # larger number or token, which must NOT be read as a status code.
    assert not _is_rate_limited(ValueError("bad json"))
    assert not _is_rate_limited(ConnectionError("reset"))
    assert not _is_rate_limited(Exception("prompt has 4290 tokens"))
    assert not _is_rate_limited(Exception("model v429 unavailable"))


def test_rate_limit_delay_honors_retry_after_and_caps() -> None:
    exc = _RateLimited("slow down")
    exc.response = SimpleNamespace(headers={"retry-after": "7"})
    assert _rate_limit_delay(exc, 0) == 7.0

    # Absurd Retry-After is capped.
    exc.response = SimpleNamespace(headers={"retry-after": "9999"})
    assert _rate_limit_delay(exc, 0) == _RATE_LIMIT_MAX_DELAY

    # No Retry-After → positive, and never exceeds the cap even after jitter (large
    # prior_backoffs forces the base to the cap, so jitter must not push it over).
    assert 0 < _rate_limit_delay(_RateLimited("x"), 0) <= _RATE_LIMIT_MAX_DELAY
    assert _rate_limit_delay(_RateLimited("x"), 20) <= _RATE_LIMIT_MAX_DELAY


@pytest.mark.asyncio
async def test_cascade_backs_off_on_429_then_succeeds() -> None:
    success = SimpleNamespace(model="ok-model")
    completion_fn = AsyncMock(side_effect=[_RateLimited("429"), success])

    with (
        patch("src.llm.asyncio.sleep", new=AsyncMock()) as slept,
        patch("src.llm.track_usage", new=lambda *a, **k: None),
        patch("src.llm.get_model", new=_fake_model),
    ):
        result = await _completion_with_fallback_impl(
            messages=[{"role": "user", "content": "hi"}],
            completion_fn=completion_fn,
            model_priority=MODEL_PRIORITY[:2],
        )

    assert result is success
    slept.assert_awaited_once()  # waited out the 429 before trying the next model


@pytest.mark.asyncio
async def test_non_rate_limit_error_does_not_back_off() -> None:
    success = SimpleNamespace(model="ok-model")
    completion_fn = AsyncMock(side_effect=[ConnectionError("reset"), success])

    with (
        patch("src.llm.asyncio.sleep", new=AsyncMock()) as slept,
        patch("src.llm.track_usage", new=lambda *a, **k: None),
        patch("src.llm.get_model", new=_fake_model),
    ):
        result = await _completion_with_fallback_impl(
            messages=[{"role": "user", "content": "hi"}],
            completion_fn=completion_fn,
            model_priority=MODEL_PRIORITY[:2],
        )

    assert result is success
    slept.assert_not_awaited()  # a plain error falls straight through to the next model
