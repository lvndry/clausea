from __future__ import annotations

import asyncio
import importlib
import os
import random
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from src.core.logging import get_logger
from src.utils.llm_usage import track_usage

# litellm is heavy to import; defer it to first use.
if TYPE_CHECKING:
    from litellm import EmbeddingResponse, ModelResponse

logger = get_logger(__name__)


class CircuitBreakerError(Exception):
    """Raised when too many consecutive LLM failures have occurred."""

    pass


class AllModelsFailedError(Exception):
    """Raised when every model in the priority list failed for one completion request."""


CIRCUIT_BREAKER_THRESHOLD: int = 3
CIRCUIT_RESET_SECONDS: float = 300.0


class CircuitBreaker:
    """Per-key circuit breaker with time-based decay and half-open probe support.

    Tracks consecutive failures for a single scope (e.g. a product slug).  When the
    failure count reaches ``CIRCUIT_BREAKER_THRESHOLD`` the circuit opens and rejects
    all requests until ``CIRCUIT_RESET_SECONDS`` have elapsed, at which point it enters
    a half-open state and allows exactly one probe.  A successful probe closes the
    circuit; a failed probe re-opens it.
    """

    def __init__(self) -> None:
        self._consecutive_failures: int = 0
        self._last_failure_time: float = 0.0
        self._is_open: bool = False
        self._half_open: bool = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        self._last_failure_time = time.monotonic()
        self._half_open = False
        if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            self._is_open = True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._last_failure_time = 0.0
        self._is_open = False
        self._half_open = False

    def reset_half_open(self) -> None:
        self._half_open = False

    def allow_request(self) -> bool:
        if not self._is_open:
            return True
        if self._half_open:
            return False
        now = time.monotonic()
        if now - self._last_failure_time >= CIRCUIT_RESET_SECONDS:
            self._half_open = True
            return True
        return False


_circuit_breakers: dict[str, CircuitBreaker] = {}


def product_circuit_key(product_slug: str) -> str:
    """Scope circuit-breaker state to one product (bulk pipeline jobs must not share one breaker)."""
    return f"product:{product_slug}"


def document_circuit_key(document: Any) -> str:
    """Circuit key for a policy document row (prefers slug in metadata, else product_id)."""
    if document is None:
        return product_circuit_key("unknown")
    if isinstance(document, dict):
        meta = document.get("metadata") or {}
        product_id = document.get("product_id")
        doc_id = document.get("id") or document.get("_id", "unknown")
    else:
        meta = getattr(document, "metadata", None) or {}
        product_id = getattr(document, "product_id", None)
        doc_id = getattr(document, "id", "unknown")
    slug = meta.get("product_slug") if isinstance(meta, dict) else None
    if isinstance(slug, str) and slug.strip():
        return product_circuit_key(slug.strip())
    if isinstance(product_id, str) and product_id.strip():
        return product_circuit_key(product_id.strip())
    return product_circuit_key(str(doc_id))


def get_circuit_breaker(key: str) -> CircuitBreaker:
    if key not in _circuit_breakers:
        _circuit_breakers[key] = CircuitBreaker()
    return _circuit_breakers[key]


class Model:
    model: str
    api_key: str
    api_base: str | None
    extra_headers: dict[str, str] | None

    def __init__(
        self,
        model: str,
        api_key: str,
        api_base: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.extra_headers = extra_headers


SupportedModel = str

# Smallest context in this cascade: gemma-4-31b-it (262K). gpt-oss-120b (131K) was
# removed — it blocked whole-document extraction and adaptive chunk sizing.
MODEL_PRIORITY: list[SupportedModel] = [
    "openrouter/openrouter/owl-alpha",
    "openrouter/google/gemma-4-31b-it:free",
    "openrouter/deepseek/deepseek-v4-flash",
    "openrouter/qwen/qwen3.5-flash-02-23",
    "openrouter/google/gemini-2.5-flash-lite",
]

# Conservative input budget for extraction (tokens). Used to choose whole-doc vs chunked.
EXTRACTION_MIN_CONTEXT_TOKENS = 250_000
EscalationValidator = Callable[[str], bool]


def get_model(model_name: SupportedModel) -> Model:
    if model_name.startswith("gemini"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        mapping = {
            "gemini-2.0-flash": "gemini/gemini-2.0-flash",
            "gemini-2.5-flash-lite": "gemini/gemini-2.5-flash-lite",
        }
        return Model(model=mapping.get(model_name, f"gemini/{model_name}"), api_key=api_key)

    if model_name.startswith("voyage"):
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key:
            raise ValueError("VOYAGE_API_KEY is not set")
        return Model(model=f"voyage/{model_name}", api_key=api_key)

    if model_name.startswith("openrouter/"):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set")
        return Model(
            model=model_name,
            api_key=api_key,
            extra_headers={
                "HTTP-Referer": os.getenv("APP_URL", "https://clausea.co"),
                "X-Title": os.getenv("APP_NAME", "Clausea"),
            },
        )

    raise ValueError(f"Unsupported model: {model_name}")


_RATE_LIMIT_BASE_DELAY = float(os.getenv("LLM_RATE_LIMIT_BASE_DELAY", "2"))
_RATE_LIMIT_MAX_DELAY = float(os.getenv("LLM_RATE_LIMIT_MAX_DELAY", "30"))


def _retry_after_seconds(exc: Exception) -> float | None:
    """Provider-supplied Retry-After (seconds), if present on the exception's response."""
    try:
        headers = getattr(getattr(exc, "response", None), "headers", None) or {}
        value = headers.get("retry-after") or headers.get("Retry-After")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _rate_limit_delay(exc: Exception, prior_backoffs: int) -> float:
    """Seconds to wait before the next attempt after a 429.

    Honors an explicit Retry-After when the provider gives one; otherwise uses jittered
    exponential backoff, capped so a fully rate-limited cascade stays bounded.
    """
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return min(retry_after, _RATE_LIMIT_MAX_DELAY)
    delay = min(_RATE_LIMIT_BASE_DELAY * (2**prior_backoffs), _RATE_LIMIT_MAX_DELAY)
    return min(delay + random.uniform(0, delay * 0.25), _RATE_LIMIT_MAX_DELAY)


async def _heartbeat_ping(heartbeat: Callable[[], Awaitable[None] | None] | None) -> None:
    if heartbeat is not None:
        await _maybe_await_impl(heartbeat())


async def _maybe_await_impl(coroutine: Awaitable[None] | None) -> None:
    if asyncio.iscoroutine(coroutine):
        await coroutine


async def _completion_with_fallback_impl(
    messages: list[dict[str, str]],
    completion_fn: Callable[..., Awaitable[ModelResponse]],
    model_priority: list[SupportedModel] | None = None,
    validator: EscalationValidator | None = None,
    heartbeat_callback: Callable[[], Awaitable[None] | None] | None = None,
    reasoning_effort: str | None = None,
    **kwargs: Any,
) -> ModelResponse:
    import litellm

    models_to_try = model_priority.copy() if model_priority else MODEL_PRIORITY.copy()
    last_exception: Exception | None = None
    # A response that returned cleanly but failed the quality validator. If every
    # model fails validation we return the last one anyway — partial data beats
    # blocking the pipeline.
    last_unvalidated: ModelResponse | None = None
    rate_limit_backoffs = 0

    for model_name in models_to_try:
        await _heartbeat_ping(heartbeat_callback)
        model = get_model(model_name)
        logger.debug("Attempting completion with model: %s (%s)", model_name, model.model)

        call_kwargs = kwargs.copy()
        # All OpenRouter models in MODEL_PRIORITY support reasoning; default medium
        # when the caller does not specify an effort level.
        effort = reasoning_effort or ("medium" if model_name.startswith("openrouter/") else None)
        if effort and "reasoning_effort" not in call_kwargs:
            call_kwargs["reasoning_effort"] = effort

        try:
            start_time = time.time()
            response = await completion_fn(
                model=model.model,
                api_key=model.api_key,
                messages=messages,
                **({"api_base": model.api_base} if model.api_base else {}),
                **({"extra_headers": model.extra_headers} if model.extra_headers else {}),
                **call_kwargs,
            )
            duration = time.time() - start_time
            provider_model = getattr(response, "model", None) or model.model
            track_usage(response, model_name, provider_model, duration=duration)
        except Exception as e:
            last_exception = e
            if isinstance(e, litellm.exceptions.RateLimitError):
                delay = _rate_limit_delay(e, rate_limit_backoffs)
                rate_limit_backoffs += 1
                logger.warning(
                    "Model %s rate-limited (429); backing off %.1fs before next model",
                    model_name,
                    delay,
                )
                await _heartbeat_ping(heartbeat_callback)
                await asyncio.sleep(delay)
            else:
                logger.warning("Model %s failed: %s. Trying next model...", model_name, e)
            continue

        if validator is not None:
            try:
                valid = validator(_extract_json_from_response(response))
            except ValueError:
                valid = False
            if not valid:
                logger.warning("Model %s failed validation, escalating to next model", model_name)
                last_unvalidated = response
                continue

        logger.debug("Successfully completed with model: %s", model_name)
        return response

    if last_unvalidated is not None:
        logger.warning("All models failed validation — returning last response anyway")
        return last_unvalidated

    error_msg = (
        f"All {len(models_to_try)} models failed. "
        f"Tried: {', '.join(models_to_try)}. "
        f"Last error: {last_exception}"
    )
    logger.error(error_msg)
    raise AllModelsFailedError(error_msg) from last_exception


async def acompletion_with_fallback(
    messages: list[dict[str, str]],
    model_priority: list[SupportedModel] | None = None,
    validator: EscalationValidator | None = None,
    circuit_key: str | None = None,
    heartbeat_callback: Callable[[], Awaitable[None] | None] | None = None,
    reasoning_effort: str | None = None,
    **kwargs: Any,
) -> ModelResponse:
    """Execute LLM completion, walking ``model_priority`` (default MODEL_PRIORITY) on failure.

    A model is skipped when the call raises, or — when ``validator`` is given — when its
    output fails validation. Since the list runs cheapest-to-most-capable, a validation
    failure naturally escalates to a stronger model.

    When ``circuit_key`` is set (e.g. :func:`product_circuit_key`), consecutive failures
    for that scope open a breaker that blocks only the same key — not other products.
    When ``circuit_key`` is omitted, no circuit breaker is applied.

    Args:
        heartbeat_callback: Optional async no-arg callable fired before each model attempt
            and before each rate-limit backoff sleep, so the caller can bump a pipeline
            job heartbeat and avoid stall-guard kills during long fallback sequences.
        reasoning_effort: Optional reasoning effort level (e.g. "medium", "high").
            Defaults to "medium" for OpenRouter models if not specified.
    """
    cb = get_circuit_breaker(circuit_key) if circuit_key is not None else None

    if cb is not None and not cb.allow_request():
        raise CircuitBreakerError("LLM service unavailable: too many consecutive failures")

    # Load the heavy litellm import off the event loop on first use; cached afterward.
    await asyncio.to_thread(importlib.import_module, "litellm")
    from litellm import acompletion

    try:
        result = await _completion_with_fallback_impl(
            messages=messages,
            completion_fn=acompletion,
            model_priority=model_priority,
            validator=validator,
            heartbeat_callback=heartbeat_callback,
            reasoning_effort=reasoning_effort,
            **kwargs,
        )
    except AllModelsFailedError:
        if cb is not None:
            cb.record_failure()
            if not cb.allow_request():
                raise CircuitBreakerError(
                    "LLM service unavailable: too many consecutive failures"
                ) from None
        raise
    except BaseException:
        if cb is not None and cb.is_open:
            cb.reset_half_open()
        raise
    else:
        if cb is not None:
            cb.record_success()
        return result


async def get_embeddings(
    input: str | list[str],
    input_type: str | None = None,
    model_name: SupportedModel = "voyage-law-2",
) -> EmbeddingResponse:
    """Generate embeddings using the specified model."""
    await asyncio.to_thread(importlib.import_module, "litellm")
    import litellm

    model = get_model(model_name)
    try:
        kwargs: dict[str, Any] = {
            "model": model.model,
            "api_key": model.api_key,
            "input": input if isinstance(input, list) else [input],
        }
        if input_type:
            kwargs["input_type"] = input_type
        response: EmbeddingResponse = await litellm.aembedding(**kwargs)
        return response
    except Exception as e:
        logger.error("Error getting embeddings with %s: %s", model_name, e)
        raise


def _extract_json_from_response(response: ModelResponse) -> str:
    choice = response.choices[0]
    if not hasattr(choice, "message"):
        raise ValueError("Response missing message attribute")
    message = choice.message  # type: ignore[attr-defined]
    if not message:
        raise ValueError("Response message is None")
    content = message.content  # type: ignore[attr-defined]
    if not content:
        raise ValueError("Response content is empty")
    return content
