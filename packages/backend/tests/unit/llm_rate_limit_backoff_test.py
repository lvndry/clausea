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

import litellm
import pytest

from src.llm import (
    _RATE_LIMIT_MAX_DELAY,
    MODEL_PRIORITY,
    Model,
    _completion_with_fallback_impl,
    _rate_limit_delay,
)

_fake_model = lambda _name: Model(model="test-model", api_key="test-key")  # noqa: E731


def _rate_limit_error(message: str = "429 too many requests") -> litellm.exceptions.RateLimitError:
    return litellm.exceptions.RateLimitError(
        message=message, llm_provider="openrouter", model="test-model"
    )


class _ErrorWithResponse(Exception):
    """Stand-in for an error carrying a Retry-After header, for delay-calculation tests."""

    response: object = None


def test_rate_limit_delay_honors_retry_after_and_caps() -> None:
    exc = _ErrorWithResponse()
    exc.response = SimpleNamespace(headers={"retry-after": "7"})
    assert _rate_limit_delay(exc, 0) == 7.0

    exc.response = SimpleNamespace(headers={"retry-after": "9999"})
    assert _rate_limit_delay(exc, 0) == _RATE_LIMIT_MAX_DELAY

    assert 0 < _rate_limit_delay(_ErrorWithResponse(), 0) <= _RATE_LIMIT_MAX_DELAY
    assert _rate_limit_delay(_ErrorWithResponse(), 20) <= _RATE_LIMIT_MAX_DELAY


@pytest.mark.asyncio
async def test_cascade_backs_off_on_429_then_succeeds() -> None:
    success = SimpleNamespace(model="ok-model")
    completion_fn = AsyncMock(side_effect=[_rate_limit_error(), success])

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
    slept.assert_awaited_once()


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
    slept.assert_not_awaited()
