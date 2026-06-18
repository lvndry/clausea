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


_consecutive_total_failures: int = 0
_CIRCUIT_BREAKER_THRESHOLD: int = 3


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
_OPENROUTER_ALIASES: dict[str, str] = {
    "openrouter/owl-alpha": os.getenv(
        "OPENROUTER_OWL_ALPHA_MODEL", "openrouter/openrouter/owl-alpha"
    ),
    "openrouter/gpt-oss-120b-free": os.getenv(
        "OPENROUTER_GPT_OSS_FREE_MODEL", "openrouter/openai/gpt-oss-120b:free"
    ),
    "openrouter/gemma-free": os.getenv(
        "OPENROUTER_GEMMA_FREE_MODEL", "openrouter/google/gemma-4-31b-it:free"
    ),
}

MODEL_PRIORITY: list[SupportedModel] = [
    "openrouter/owl-alpha",
    "openrouter/gpt-oss-120b-free",
    "openrouter/gemma-free",
    "openrouter/openai/gpt-oss-120b",
    "openrouter/deepseek/deepseek-v4-flash",
    "openrouter/qwen/qwen3.5-flash-02-23",
    "openrouter/google/gemini-2.5-flash-lite",
]
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
        full_model = _OPENROUTER_ALIASES.get(model_name, model_name)
        return Model(
            model=full_model,
            api_key=api_key,
            extra_headers={
                "HTTP-Referer": os.getenv("APP_URL", "https://clausea.co"),
                "X-Title": os.getenv("APP_NAME", "Clausea"),
            },
        )

    raise ValueError(f"Unsupported model: {model_name}")


# Rate-limit backoff. The model cascade shares one OpenRouter account/key, so an
# account-level 429 hits every model at once. Without spacing, the whole cascade (and
# the caller's retries) fires within seconds and lands inside the same rate-limit window.
# Backing off on a 429 spreads attempts across tens of seconds so a brief window passes.
_RATE_LIMIT_BASE_DELAY = float(os.getenv("LLM_RATE_LIMIT_BASE_DELAY", "2"))
_RATE_LIMIT_MAX_DELAY = float(os.getenv("LLM_RATE_LIMIT_MAX_DELAY", "30"))


def _is_rate_limited(exc: Exception) -> bool:
    """True if an LLM call failed because of rate limiting (HTTP 429)."""
    if getattr(exc, "status_code", None) == 429:
        return True
    name = type(exc).__name__.lower()
    return "ratelimit" in name or "429" in str(exc)


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
    return delay + random.uniform(0, delay * 0.25)


async def _completion_with_fallback_impl(
    messages: list[dict[str, str]],
    completion_fn: Callable[..., Awaitable[ModelResponse]],
    model_priority: list[SupportedModel] | None = None,
    validator: EscalationValidator | None = None,
    **kwargs: Any,
) -> ModelResponse:
    models_to_try = model_priority.copy() if model_priority else MODEL_PRIORITY.copy()
    last_exception: Exception | None = None
    # A response that returned cleanly but failed the quality validator. If every
    # model fails validation we return the last one anyway — partial data beats
    # blocking the pipeline.
    last_unvalidated: ModelResponse | None = None
    rate_limit_backoffs = 0

    for model_name in models_to_try:
        model = get_model(model_name)
        logger.debug("Attempting completion with model: %s (%s)", model_name, model.model)

        try:
            start_time = time.time()
            response = await completion_fn(
                model=model.model,
                api_key=model.api_key,
                messages=messages,
                **({"api_base": model.api_base} if model.api_base else {}),
                **({"extra_headers": model.extra_headers} if model.extra_headers else {}),
                **kwargs,
            )
            duration = time.time() - start_time
            provider_model = getattr(response, "model", None) or model.model
            track_usage(response, model_name, provider_model, duration=duration)
        except Exception as e:
            last_exception = e
            # On a 429, the shared account is throttled, so the next model would likely
            # 429 too — wait out the window before moving on. Other errors fall straight
            # through to the next model.
            if _is_rate_limited(e):
                delay = _rate_limit_delay(e, rate_limit_backoffs)
                rate_limit_backoffs += 1
                logger.warning(
                    "Model %s rate-limited (429); backing off %.1fs before next model",
                    model_name,
                    delay,
                )
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
    **kwargs: Any,
) -> ModelResponse:
    """Execute LLM completion, walking ``model_priority`` (default MODEL_PRIORITY) on failure.

    A model is skipped when the call raises, or — when ``validator`` is given — when its
    output fails validation. Since the list runs cheapest-to-most-capable, a validation
    failure naturally escalates to a stronger model.
    """
    global _consecutive_total_failures

    if _consecutive_total_failures >= _CIRCUIT_BREAKER_THRESHOLD:
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
            **kwargs,
        )
    except AllModelsFailedError:
        _consecutive_total_failures += 1
        if _consecutive_total_failures >= _CIRCUIT_BREAKER_THRESHOLD:
            raise CircuitBreakerError(
                "LLM service unavailable: too many consecutive failures"
            ) from None
        raise
    else:
        _consecutive_total_failures = 0
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
