"""Unit tests for the per-key LLM circuit breaker."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from src import llm as llm_module
from src.llm import (
    CIRCUIT_BREAKER_THRESHOLD,
    CIRCUIT_RESET_SECONDS,
    AllModelsFailedError,
    CircuitBreaker,
    CircuitBreakerError,
    acompletion_with_fallback,
    document_circuit_key,
    get_circuit_breaker,
    product_circuit_key,
    reset_circuit_breakers,
)


@pytest.fixture(autouse=True)
def _reset_breakers(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_circuit_breakers()
    monkeypatch.setattr(llm_module, "LLM_CIRCUIT_BREAKER_ENABLED", True)


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
    for _ in range(CIRCUIT_BREAKER_THRESHOLD):
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


def test_document_circuit_key_scopes_per_document() -> None:
    assert document_circuit_key(None) == product_circuit_key("unknown", "document")
    assert document_circuit_key({"product_id": "pid-1", "id": "doc-1"}) == product_circuit_key(
        "pid-1", "doc:doc-1"
    )
    assert document_circuit_key(
        {"metadata": {"product_slug": "discord"}, "product_id": "pid-1", "id": "doc-9"}
    ) == product_circuit_key("discord", "doc:doc-9")


@pytest.mark.asyncio
async def test_breaker_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "LLM_CIRCUIT_BREAKER_ENABLED", False)
    reset_circuit_breakers()

    with patch(
        "src.llm._completion_with_fallback_impl",
        AsyncMock(side_effect=AllModelsFailedError("all failed")),
    ):
        for _ in range(CIRCUIT_BREAKER_THRESHOLD + 2):
            with pytest.raises(AllModelsFailedError):
                await acompletion_with_fallback(
                    messages=[{"role": "user", "content": "hi"}],
                    circuit_key=product_circuit_key("alpha", "overview"),
                )


@pytest.mark.asyncio
async def test_config_errors_do_not_trip_breaker() -> None:
    cb = get_circuit_breaker("config-error-test")

    class UnsupportedParamsError(Exception):
        pass

    err = AllModelsFailedError("all failed")
    err.__cause__ = UnsupportedParamsError(
        "openrouter does not support parameters: ['reasoning_effort']"
    )

    with patch("src.llm._completion_with_fallback_impl", AsyncMock(side_effect=err)):
        with pytest.raises(AllModelsFailedError):
            await acompletion_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                circuit_key="config-error-test",
            )

    assert cb.consecutive_failures == 0


@pytest.mark.asyncio
async def test_product_circuit_keys_are_isolated() -> None:
    """Failures for one product must not trip the breaker for another."""
    product_a = product_circuit_key("alpha", "overview")
    product_b = product_circuit_key("beta", "overview")
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
