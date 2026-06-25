"""Unit tests for the per-key LLM circuit breaker."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.llm import (
    CIRCUIT_BREAKER_THRESHOLD,
    CIRCUIT_RESET_SECONDS,
    AllModelsFailedError,
    CircuitBreaker,
    CircuitBreakerError,
    acompletion_with_fallback,
    get_circuit_breaker,
    product_circuit_key,
)


def test_reset_half_open_allows_subsequent_probe() -> None:
    cb = CircuitBreaker()
    cb._is_open = True
    cb._half_open = True

    cb.reset_half_open()

    assert cb._half_open is False
    assert cb.is_open is True


@pytest.mark.asyncio
async def test_cancelled_probe_resets_half_open() -> None:
    cb = get_circuit_breaker("cancel-probe-test")
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open is True

    cb._last_failure_time = time.monotonic() - CIRCUIT_RESET_SECONDS - 1

    with patch(
        "src.llm._completion_with_fallback_impl", AsyncMock(side_effect=asyncio.CancelledError())
    ):
        with pytest.raises(asyncio.CancelledError):
            await acompletion_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                circuit_key="cancel-probe-test",
            )

    assert cb._half_open is False


@pytest.mark.asyncio
async def test_all_models_failed_still_records_failure() -> None:
    cb = get_circuit_breaker("failure-test")
    cb.record_success()

    with patch(
        "src.llm._completion_with_fallback_impl",
        AsyncMock(side_effect=AllModelsFailedError("all failed")),
    ):
        with pytest.raises(AllModelsFailedError):
            await acompletion_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                circuit_key="failure-test",
            )

    assert cb.consecutive_failures == 1


@pytest.mark.asyncio
async def test_no_circuit_key_skips_breaker_on_all_models_failed() -> None:
    """Without circuit_key, failures must not open a shared breaker for later calls."""
    with patch(
        "src.llm._completion_with_fallback_impl",
        AsyncMock(side_effect=AllModelsFailedError("all failed")),
    ):
        with pytest.raises(AllModelsFailedError):
            await acompletion_with_fallback(messages=[{"role": "user", "content": "hi"}])

        # Second call still attempts the LLM (not short-circuited).
        with pytest.raises(AllModelsFailedError):
            await acompletion_with_fallback(messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_product_circuit_keys_are_isolated() -> None:
    """Failures for one product must not trip the breaker for another."""
    product_a = product_circuit_key("alpha")
    product_b = product_circuit_key("beta")
    cb_a = get_circuit_breaker(product_a)
    cb_b = get_circuit_breaker(product_b)
    cb_a.record_success()
    cb_b.record_success()

    with patch(
        "src.llm._completion_with_fallback_impl",
        AsyncMock(side_effect=AllModelsFailedError("all failed")),
    ):
        for _ in range(CIRCUIT_BREAKER_THRESHOLD - 1):
            with pytest.raises(AllModelsFailedError):
                await acompletion_with_fallback(
                    messages=[{"role": "user", "content": "hi"}],
                    circuit_key=product_a,
                )
        with pytest.raises(CircuitBreakerError):
            await acompletion_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                circuit_key=product_a,
            )

    assert get_circuit_breaker(product_a).is_open is True

    ok_response = AsyncMock()
    ok_response.model = "test-model"
    with patch(
        "src.llm._completion_with_fallback_impl",
        AsyncMock(return_value=ok_response),
    ):
        result = await acompletion_with_fallback(
            messages=[{"role": "user", "content": "hi"}],
            circuit_key=product_b,
        )

    assert result is ok_response
    assert get_circuit_breaker(product_b).is_open is False
