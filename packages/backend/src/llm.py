import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import litellm
from litellm import EmbeddingResponse, ModelResponse, acompletion

from src.core.logging import get_logger
from src.utils.llm_usage import track_usage

logger = get_logger(__name__)


class Model:
    model: str
    api_key: str

    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key


SupportedModel = Literal[
    # openai
    "gpt-5.2",
    "gpt-5.2-pro",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-pro",
    "gpt-5-mini",
    "gpt-5-nano",
    # gemini
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
    # anthropic
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
    # mistral
    "mistral-small",
    "mistral-medium",
    "mistral-large",
    # voyage
    "voyage-law-2",
    # xai
    "grok-4-1-fast-reasoning",
    "grok-4-1-fast-non-reasoning",
    # openrouter
    "kimi-k2-thinking",
]

DEFAULT_MODEL_PRIORITY: list[SupportedModel] = [
    "gemini-3-flash-preview",
    "grok-4-1-fast-non-reasoning",
    "gpt-5-mini",
    "kimi-k2-thinking",
    "claude-haiku-4-5",
]


def _sanitize_model_kwargs(model_name: SupportedModel, kwargs: dict[str, Any]) -> dict[str, Any]:
    """
    Remove or adjust parameters that are incompatible with a specific model.
    """
    sanitized_kwargs = dict(kwargs)

    if model_name in {"gpt-5-mini", "gpt-5-nano", "gemini-3-flash-preview"}:
        temperature = sanitized_kwargs.get("temperature")
        if temperature is not None and temperature != 1:
            logger.debug(
                "Removing unsupported temperature override (%s) for model %s",
                temperature,
                model_name,
            )
            sanitized_kwargs.pop("temperature", None)

    return sanitized_kwargs


def get_model(model_name: SupportedModel) -> Model:
    # OpenAI models (gpt-*)
    if model_name.startswith("gpt"):
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set")

        return Model(
            model=model_name,
            api_key=OPENAI_API_KEY,
        )
    # Gemini models (gemini-*)
    elif model_name.startswith("gemini"):
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set")

        # Use mapping for known models, fallback to gemini/{model_name} format
        model_mapping = {
            "gemini-2.0-flash": "gemini/gemini-2.0-flash",
            "gemini-2.5-flash-lite": "gemini/gemini-2.5-flash-lite",
        }

        full_model = model_mapping.get(model_name, f"gemini/{model_name}")
        return Model(
            model=full_model,
            api_key=GEMINI_API_KEY,
        )
    # Anthropic models (claude-*)
    elif model_name.startswith("claude"):
        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set")

        # Use mapping for models that need specific version suffixes
        model_mapping = {
            "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
            "claude-3-opus": "claude-3-opus-20240229",
            "claude-3-sonnet": "claude-3-sonnet-20240229",
            "claude-3-haiku": "claude-3-haiku-20240307",
        }

        full_model = model_mapping.get(model_name, model_name)
        return Model(
            model=full_model,
            api_key=ANTHROPIC_API_KEY,
        )
    # XAI models (grok-*)
    elif model_name.startswith("grok"):
        XAI_API_KEY = os.getenv("XAI_API_KEY")
        if not XAI_API_KEY:
            raise ValueError("XAI_API_KEY is not set")

        return Model(
            model=f"xai/{model_name}",
            api_key=XAI_API_KEY,
        )
    # Mistral models (mistral-*)
    elif model_name.startswith("mistral"):
        MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
        if not MISTRAL_API_KEY:
            raise ValueError("MISTRAL_API_KEY is not set")

        # Use mapping for known models, fallback to mistral/{model_name} format
        model_mapping = {
            "mistral-small": "mistral/mistral-small-latest",
            "mistral-medium": "mistral/mistral-medium-latest",
        }

        full_model = model_mapping.get(model_name, f"mistral/{model_name}")
        return Model(
            model=full_model,
            api_key=MISTRAL_API_KEY,
        )
    # Voyage models (voyage-*)
    elif model_name.startswith("voyage"):
        VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
        if not VOYAGE_API_KEY:
            raise ValueError("VOYAGE_API_KEY is not set")

        return Model(
            model=f"voyage/{model_name}",
            api_key=VOYAGE_API_KEY,
        )
    # OpenRouter models (kimi-*)
    elif model_name.startswith("kimi"):
        OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
        if not OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not set")

        # Map model names to OpenRouter format: openrouter/{provider}/{model}
        model_mapping = {
            "kimi-k2-thinking": "openrouter/moonshotai/kimi-k2-thinking",
        }

        full_model = model_mapping.get(model_name, f"openrouter/{model_name}")
        return Model(
            model=full_model,
            api_key=OPENROUTER_API_KEY,
        )
    else:
        raise ValueError(f"Unsupported model: {model_name}")


async def _completion_with_fallback_impl(
    messages: list[dict[str, str]],
    completion_fn: Callable[..., Awaitable[ModelResponse]],
    model_priority: list[SupportedModel] | None = None,
    **kwargs: Any,
) -> ModelResponse:
    """
    Internal implementation of completion with fallback logic.

    Args:
        messages: List of message dicts for the LLM
        completion_fn: Async callable that performs the completion (acompletion or wrapped completion)
        model_priority: Optional list of models to try in order. If None, uses DEFAULT_MODEL_PRIORITY.
        **kwargs: Additional arguments to pass to completion function

    Returns:
        ModelResponse from the first model that succeeds

    Raises:
        Exception: If all models fail, raises the last exception encountered
    """
    # Use provided priority or default
    models_to_try = model_priority.copy() if model_priority else DEFAULT_MODEL_PRIORITY.copy()
    last_exception: Exception | None = None

    # Try each model in order until one succeeds
    for model_name in models_to_try:
        model = get_model(model_name)
        logger.debug(f"Attempting completion with model: {model_name} ({model.model})")

        try:
            call_kwargs = _sanitize_model_kwargs(model_name, kwargs)
            start_time = time.time()
            response = await completion_fn(
                model=model.model,
                api_key=model.api_key,
                messages=messages,
                **call_kwargs,
            )
            duration = time.time() - start_time

            # Success - return immediately
            logger.debug(f"Successfully completed with model: {model_name}")

            # Track usage automatically via context
            provider_model = getattr(response, "model", None) or model.model
            track_usage(response, model_name, provider_model, duration=duration)

            return response

        except Exception as e:
            last_exception = e
            logger.warning(f"Model {model_name} failed: {e}. Trying next model...")
            # Continue to next model
            continue

    # All models failed
    error_msg = (
        f"All {len(models_to_try)} models failed. "
        f"Tried: {', '.join(models_to_try)}. "
        f"Last error: {last_exception}"
    )
    logger.error(error_msg)
    raise Exception(error_msg) from last_exception


async def acompletion_with_fallback(
    messages: list[dict[str, str]],
    model_priority: list[SupportedModel] | None = None,
    **kwargs: Any,
) -> ModelResponse:
    """
    Execute LLM completion with fallback to alternative models on failure.

    Tries models in priority order until one succeeds. Each call is independent
    and does not maintain state across calls (thread-safe for concurrent use).

    Usage tracking is automatic via context variables. Set a tracker using:
    - set_usage_tracker(callback) from src.utils.llm_usage for the current context
    - usage_tracking(callback) from src.utils.llm_usage as an async context manager

    Args:
        messages: List of message dicts for the LLM
        model_priority: Optional list of models to try in order. If None, uses DEFAULT_MODEL_PRIORITY.
        **kwargs: Additional arguments to pass to acompletion (temperature, response_format, etc.)

    Returns:
        ModelResponse from the first model that succeeds

    Raises:
        Exception: If all models fail, raises the last exception encountered
    """
    return await _completion_with_fallback_impl(
        messages=messages,
        completion_fn=acompletion,
        model_priority=model_priority,
        **kwargs,
    )


def completion_with_fallback(
    messages: list[dict[str, str]],
    model_priority: list[SupportedModel] | None = None,
    **kwargs: Any,
) -> ModelResponse:
    """
    Synchronous version of acompletion_with_fallback for non-async contexts.

    Execute LLM completion with fallback to alternative models on failure.

    Tries models in priority order until one succeeds. Each call is independent
    and does not maintain state across calls (thread-safe for concurrent use).

    Usage tracking is automatic via context variables. Set a tracker using:
    - set_usage_tracker(callback) from src.utils.llm_usage for the current context

    Args:
        messages: List of message dicts for the LLM
        model_priority: Optional list of models to try in order. If None, uses DEFAULT_MODEL_PRIORITY.
        **kwargs: Additional arguments to pass to completion (temperature, response_format, etc.)

    Returns:
        ModelResponse from the first model that succeeds

    Raises:
        Exception: If all models fail, raises the last exception encountered
    """
    return asyncio.run(
        _completion_with_fallback_impl(
            messages=messages,
            completion_fn=acompletion,
            model_priority=model_priority,
            **kwargs,
        )
    )


async def get_embeddings(
    input: str | list[str],
    input_type: Literal["query", "document"] | None = None,
    model_name: SupportedModel = "voyage-law-2",
) -> EmbeddingResponse:
    """
    Generate embeddings for text input using the specified model.

    Args:
        input: Single text string or list of text strings to embed
        input_type: Optional type of input - "query" for search queries, "document" for documents.
                   Some models (like voyage-law-2) use this to optimize embeddings.
        model_name: The model to use for embeddings (default: "voyage-law-2")

    Returns:
        EmbeddingResponse containing the embeddings and metadata

    Raises:
        Exception: If embedding generation fails
    """
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
        logger.error(f"Error getting embeddings with {model_name}: {str(e)}")
        raise
