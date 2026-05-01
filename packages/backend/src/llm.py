import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

import litellm
from litellm import EmbeddingResponse, ModelResponse, acompletion

from src.core.logging import get_logger
from src.utils.llm_usage import track_usage

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


# Model identifier strings. Supported prefixes:
#   gpt-*            → OpenAI          (OPENAI_API_KEY)
#   gemini/*         → Google          (GEMINI_API_KEY)
#   claude-*         → Anthropic       (ANTHROPIC_API_KEY)
#   grok-*           → xAI             (XAI_API_KEY)
#   mistral-*        → Mistral direct  (MISTRAL_API_KEY)
#   voyage-*         → Voyage          (VOYAGE_API_KEY)
#   openrouter/*     → OpenRouter      (OPENROUTER_API_KEY)
#   groq/*           → Groq            (GROQ_API_KEY)
#   together/*       → Together AI     (TOGETHER_API_KEY)
#   ollama/*         → local Ollama    (OLLAMA_BASE_URL, default http://localhost:11434)
#   vllm/*           → local vLLM/llama.cpp/LM Studio (VLLM_BASE_URL, default http://localhost:8000/v1)
SupportedModel = str

DEFAULT_MODEL_PRIORITY: list[SupportedModel] = [
    "gpt-5-nano",
    "openrouter/mistral-small",
    "openrouter/free",
]

# Short aliases → full LiteLLM model identifiers for OpenRouter models.
# "openrouter/free" resolves to a capable free-tier model; override via OPENROUTER_FREE_MODEL.
_OPENROUTER_ALIASES: dict[str, str] = {
    "openrouter/mistral-small": "openrouter/mistral/mistral-small",
    "openrouter/free": os.getenv(
        "OPENROUTER_FREE_MODEL", "openrouter/meta-llama/llama-3.1-8b-instruct:free"
    ),
    "openrouter/gpt-oss-120b-nitro": "openrouter/openai/gpt-oss-120b:nitro",
    "openrouter/deepseek-v4-flash": "openrouter/deepseek/deepseek-v4-flash",
    "openrouter/grok-4.1-fast": "openrouter/x-ai/grok-4.1-fast",
    # legacy
    "openrouter/kimi-k2-thinking": "openrouter/moonshotai/kimi-k2-thinking",
}

EscalationValidator = Callable[[str], bool]

_NO_TEMPERATURE_MODELS: frozenset[str] = frozenset(
    {"gpt-5-mini", "gpt-5.4-mini", "gpt-5-nano", "gemini-3-flash-preview"}
)


def _sanitize_model_kwargs(model_name: SupportedModel, kwargs: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(kwargs)

    if model_name in _NO_TEMPERATURE_MODELS:
        if sanitized.get("temperature") not in (None, 1):
            logger.debug("Removing unsupported temperature for %s", model_name)
            sanitized.pop("temperature", None)

    if model_name.startswith(("ollama/", "vllm/")):
        if not sanitized.get("tools"):
            sanitized.pop("tool_choice", None)

    return sanitized


def get_model(model_name: SupportedModel) -> Model:
    if model_name.startswith("gpt"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        return Model(model=model_name, api_key=api_key)

    if model_name.startswith("gemini"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        mapping = {
            "gemini-2.0-flash": "gemini/gemini-2.0-flash",
            "gemini-2.5-flash-lite": "gemini/gemini-2.5-flash-lite",
        }
        return Model(model=mapping.get(model_name, f"gemini/{model_name}"), api_key=api_key)

    if model_name.startswith("claude"):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        mapping = {
            "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
            "claude-3-opus": "claude-3-opus-20240229",
            "claude-3-sonnet": "claude-3-sonnet-20240229",
            "claude-3-haiku": "claude-3-haiku-20240307",
        }
        return Model(model=mapping.get(model_name, model_name), api_key=api_key)

    if model_name.startswith("grok"):
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            raise ValueError("XAI_API_KEY is not set")
        return Model(model=f"xai/{model_name}", api_key=api_key)

    if model_name.startswith("mistral"):
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY is not set")
        mapping = {
            "mistral-small": "mistral/mistral-small-latest",
            "mistral-medium": "mistral/mistral-medium-latest",
        }
        return Model(model=mapping.get(model_name, f"mistral/{model_name}"), api_key=api_key)

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

    if model_name.startswith("groq/"):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set")
        return Model(model=model_name, api_key=api_key)

    if model_name.startswith("together/"):
        api_key = os.getenv("TOGETHER_API_KEY")
        if not api_key:
            raise ValueError("TOGETHER_API_KEY is not set")
        return Model(model="together_ai/" + model_name.removeprefix("together/"), api_key=api_key)

    if model_name.startswith("ollama/"):
        return Model(
            model=model_name,
            api_key="",
            api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )

    if model_name.startswith("vllm/"):
        return Model(
            model="openai/" + model_name.removeprefix("vllm/"),
            api_key=os.getenv("VLLM_API_KEY", "local"),
            api_base=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
        )

    raise ValueError(f"Unsupported model: {model_name}")


async def _completion_with_fallback_impl(
    messages: list[dict[str, str]],
    completion_fn: Callable[..., Awaitable[ModelResponse]],
    model_priority: list[SupportedModel] | None = None,
    **kwargs: Any,
) -> ModelResponse:
    models_to_try = model_priority.copy() if model_priority else DEFAULT_MODEL_PRIORITY.copy()
    last_exception: Exception | None = None

    for model_name in models_to_try:
        model = get_model(model_name)
        logger.debug("Attempting completion with model: %s (%s)", model_name, model.model)

        try:
            call_kwargs = _sanitize_model_kwargs(model_name, kwargs)
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
            logger.debug("Successfully completed with model: %s", model_name)
            provider_model = getattr(response, "model", None) or model.model
            track_usage(response, model_name, provider_model, duration=duration)
            return response

        except Exception as e:
            last_exception = e
            logger.warning("Model %s failed: %s. Trying next model...", model_name, e)
            continue

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
    **kwargs: Any,
) -> ModelResponse:
    """Execute LLM completion with fallback. Uses DEFAULT_MODEL_PRIORITY when model_priority is None."""
    global _consecutive_total_failures

    if _consecutive_total_failures >= _CIRCUIT_BREAKER_THRESHOLD:
        raise CircuitBreakerError("LLM service unavailable: too many consecutive failures")

    try:
        result = await _completion_with_fallback_impl(
            messages=messages,
            completion_fn=acompletion,
            model_priority=model_priority,
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


def completion_with_fallback(
    messages: list[dict[str, str]],
    model_priority: list[SupportedModel] | None = None,
    **kwargs: Any,
) -> ModelResponse:
    """Synchronous version of acompletion_with_fallback."""
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
    input_type: str | None = None,
    model_name: SupportedModel = "voyage-law-2",
) -> EmbeddingResponse:
    """Generate embeddings using the specified model."""
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


async def acompletion_with_escalation(
    messages: list[dict[str, str]],
    primary: list[SupportedModel],
    escalation: list[SupportedModel],
    validator: EscalationValidator,
    **kwargs: Any,
) -> ModelResponse:
    """Call primary model, validate response quality, escalate to better model on failure.

    If the escalated response also fails validation, returns it anyway with a warning —
    partial data is better than blocking the pipeline.
    """
    response = await acompletion_with_fallback(messages, model_priority=primary, **kwargs)

    try:
        content = _extract_json_from_response(response)
        primary_valid = validator(content)
    except ValueError:
        primary_valid = False

    if primary_valid:
        return response

    logger.warning(
        "Primary model %s failed validation, escalating to %s",
        response.model,
        escalation[0] if escalation else "unknown",
    )

    escalated = await acompletion_with_fallback(messages, model_priority=escalation, **kwargs)
    logger.info("Escalated completion used model %s", escalated.model)

    try:
        escalated_content = _extract_json_from_response(escalated)
        if not validator(escalated_content):
            logger.warning(
                "Escalated model %s also failed validation — returning response anyway",
                escalated.model,
            )
    except ValueError:
        logger.warning(
            "Escalated model %s returned malformed content — returning response anyway",
            escalated.model,
        )

    return escalated
