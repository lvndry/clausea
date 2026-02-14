# LLM Completion Mechanism & Resilience Architecture

## Overview

Clausea's LLM completion system is designed for **maximum resilience and operational flexibility**. The system automatically handles failures (rate limits, token exhaustion, API outages) by seamlessly falling back to alternative models and providers, ensuring high availability and reliability for our legal document analysis operations.

## Core Design Principles

### 1. **Multi-Provider Resilience**

The system supports multiple LLM providers (OpenAI, Anthropic, Google Gemini, XAI, Mistral, OpenRouter) to ensure that a failure in one provider doesn't bring down the entire service. This is critical for a production system that processes thousands of legal documents daily.

### 2. **Task-Specific Model Selection**

Different legal analysis tasks require different model capabilities:

- **Simple summarization**: Fast, cost-effective models (e.g., `gpt-5-mini`, `gemini-3-flash-preview`)
- **Complex legal reasoning**: Advanced reasoning models (e.g., `gpt-5-pro`, `grok-4-1-fast-reasoning`)
- **High-accuracy analysis**: Premium models for critical legal interpretations (e.g., `claude-opus-4-1`)

The system allows each operation to specify its preferred model priority list, enabling cost optimization while maintaining quality.

### 3. **Automatic Fallback Chain**

When a model fails, the system automatically tries the next model in the priority list until one succeeds. This happens transparently without requiring retry logic in calling code.

## Architecture

### Core Components

#### `acompletion_with_fallback()` / `completion_with_fallback()`

The primary entry points for LLM completions. Both functions share the same underlying implementation (`_completion_with_fallback_impl`) but provide async and sync interfaces respectively.

**Key Features:**

- Accepts a `model_priority` list to specify preferred models for the task
- Falls back automatically on any exception (rate limits, API errors, token exhaustion)
- Tracks usage automatically via context variables
- Thread-safe and stateless (safe for concurrent use)

**Example Usage:**

```python
# Async version (recommended)
response = await acompletion_with_fallback(
    messages=[{"role": "user", "content": "Analyze this privacy policy..."}],
    model_priority=["gpt-5-pro", "claude-sonnet-4-5", "gemini-3-pro-preview"],
    temperature=0.7,
)

# Sync version (for non-async contexts)
response = completion_with_fallback(
    messages=[{"role": "user", "content": "Analyze this privacy policy..."}],
    model_priority=["gpt-5-mini", "gemini-3-flash-preview"],
)
```

#### Model Priority Lists

Each operation can specify its preferred models in priority order. If no priority is provided, the system uses `DEFAULT_MODEL_PRIORITY`:

```python
DEFAULT_MODEL_PRIORITY = [
    "gemini-3-flash-preview",      # Fast, cost-effective
    "grok-4-1-fast-non-reasoning",  # Alternative fast model
    "gpt-5-mini",                  # OpenAI fallback
    "kimi-k2-thinking",            # OpenRouter fallback
]
```

#### Model Selection by Task Type

The system supports task-specific model selection. For example, in document summarization:

```python
def _get_model_priority(document: Document) -> list[SupportedModel]:
    """Get model priority list based on document complexity."""
    if should_use_reasoning_model(document):
        # Complex documents: prefer reasoning models
        return ["gpt-5-mini", "grok-4-1-fast-reasoning", "gemini-2.5-flash"]
    else:
        # Simple documents: use cost-effective models
        return ["gpt-5-mini", "grok-4-1-fast-non-reasoning", "gemini-2.5-flash"]
```

This allows the system to:

- Use expensive reasoning models only when needed
- Optimize costs for simple operations
- Maintain quality for complex legal analysis

## Failure Handling & Resilience

### What Triggers Fallback?

The system automatically falls back to the next model on **any exception**, including:

1. **Rate Limiting**: API rate limits are hit (429 errors)
2. **Token Exhaustion**: Account has no remaining tokens/quota
3. **API Outages**: Provider API is temporarily unavailable
4. **Model Errors**: Model-specific errors (invalid parameters, model unavailable)
5. **Network Issues**: Timeouts, connection errors
6. **Authentication Errors**: Invalid API keys (though this would fail all models)

### Fallback Behavior

1. **Sequential Fallback**: Models are tried in priority order, one at a time
2. **Immediate Return**: As soon as one model succeeds, the response is returned
3. **Error Logging**: Each failure is logged with a warning, but execution continues
4. **Final Failure**: Only if all models fail does the system raise an exception

**Example Flow:**

```
Attempt 1: gemini-3-flash-preview → Rate limit (429) → Continue
Attempt 2: grok-4-1-fast-non-reasoning → Success → Return response
```

### Error Handling

```python
try:
    response = await acompletion_with_fallback(
        messages=messages,
        model_priority=["model-1", "model-2", "model-3"],
    )
except Exception as e:
    # Only raised if ALL models failed
    logger.error(f"All models failed: {e}")
    # Handle complete failure
```

## Supported Models & Providers

### OpenAI Models

- `gpt-5.2`, `gpt-5.2-pro`, `gpt-5.1`, `gpt-5`, `gpt-5-pro`, `gpt-5-mini`, `gpt-5-nano`
- `gpt-4.1-mini`, `gpt-4o-mini`

### Google Gemini Models

- `gemini-3-flash-preview`, `gemini-3-pro-preview`
- `gemini-2.5-flash`, `gemini-2.5-flash-lite`

### Anthropic Claude Models

- `claude-haiku-4-5`, `claude-sonnet-4-5`, `claude-opus-4-1`

### XAI Grok Models

- `grok-4-1-fast-reasoning`, `grok-4-1-fast-non-reasoning`
- `grok-3-mini`

### Mistral Models

- `mistral-small`, `mistral-medium`, `mistral-large`

### OpenRouter Models

- `kimi-k2-thinking` (via OpenRouter)

### Voyage Models (Embeddings Only)

- `voyage-law-2` (specialized for legal documents)

## Model-Specific Considerations

### Parameter Sanitization

Some models don't support certain parameters. The system automatically sanitizes parameters via `_sanitize_model_kwargs()`:

- **Temperature restrictions**: Some models (e.g., `gpt-5-mini`, `gemini-3-flash-preview`) don't support custom temperature values
- **Response format**: Some models have different JSON schema requirements
- **Model-specific parameters**: Each provider may have unique parameters

### API Key Management

Each provider requires its own API key, stored as environment variables:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`
- `XAI_API_KEY`
- `MISTRAL_API_KEY`
- `VOYAGE_API_KEY`
- `OPENROUTER_API_KEY`

The system validates API keys at model selection time and raises clear errors if keys are missing.

## Usage Tracking

The system automatically tracks LLM usage via context variables. Usage tracking includes:

- **Model used**: Which model/provider handled the request
- **Token usage**: Input/output tokens consumed
- **Duration**: Request latency
- **Cost estimation**: Calculated based on provider pricing

Set up usage tracking using:

```python
from src.utils.llm_usage import set_usage_tracker, usage_tracking

# Option 1: Set tracker for current context
tracker = UsageTracker()
set_usage_tracker(tracker.create_tracker("operation_name"))

# Option 2: Use async context manager
async with usage_tracking(tracker.create_tracker("operation_name")):
    response = await acompletion_with_fallback(...)
```

## Best Practices

### 1. **Specify Model Priority for Each Task**

Don't rely on defaults. Choose models based on:

- **Task complexity**: Simple tasks → fast/cheap models, Complex tasks → reasoning models
- **Cost constraints**: Balance quality vs. cost
- **Provider diversity**: Spread across providers to reduce single points of failure

```python
# Good: Task-specific model selection
if task_requires_reasoning:
    model_priority = ["gpt-5-pro", "claude-sonnet-4-5", "grok-4-1-fast-reasoning"]
else:
    model_priority = ["gpt-5-mini", "gemini-3-flash-preview"]
```

### 2. **Order Models by Preference**

List models in order of preference (best first):

- First: Your preferred model for the task
- Middle: Good alternatives (different providers)
- Last: Fallback options (slower but reliable)

### 3. **Handle Complete Failures Gracefully**

Always wrap completion calls in try/except to handle the case where all models fail:

```python
try:
    response = await acompletion_with_fallback(...)
except Exception as e:
    # Log the failure
    logger.error(f"All models failed for task: {e}")
    # Return a graceful error or retry later
    return None
```

### 4. **Monitor Model Performance**

Track which models are being used and how often fallbacks occur:

- High fallback rates may indicate provider issues
- Model selection patterns help optimize costs
- Duration tracking helps identify slow models

## Why This Architecture?

### Problem: Single Points of Failure

Without multi-provider fallback:

- Rate limits on one provider → entire system down
- API outage → no document analysis possible
- Token exhaustion → service unavailable

### Solution: Resilient Multi-Provider System

With our architecture:

- Rate limit on OpenAI → automatically uses Gemini
- Gemini outage → falls back to Grok
- Token exhaustion on one provider → uses another provider
- **Result**: 99.9%+ uptime even with individual provider issues

### Cost Optimization

By selecting models based on task complexity:

- Simple operations use cheap models (`gpt-5-mini`, `gemini-3-flash-preview`)
- Complex operations use appropriate models (`gpt-5-pro`, `claude-sonnet-4-5`)
- **Result**: Optimal cost/quality balance

### Operational Flexibility

Different operations can use different models:

- Document summarization: Fast models for quick results
- Deep legal analysis: Premium models for accuracy
- Bulk processing: Cost-optimized models
- **Result**: Each operation optimized for its requirements

## Implementation Details

### Internal Architecture

The system uses a shared implementation (`_completion_with_fallback_impl`) that:

1. **Iterates through model priority list**
2. **Sanitizes parameters** for each model
3. **Attempts completion** with error handling
4. **Tracks usage** on success
5. **Falls back** on any exception
6. **Raises exception** only if all models fail

Both async and sync interfaces use the same implementation, ensuring consistent behavior.

### Thread Safety

The system is **stateless and thread-safe**:

- No shared state between calls
- Each call is independent
- Safe for concurrent use in async contexts
- Safe for parallel processing

## Future Enhancements

Potential improvements to the system:

1. **Intelligent Model Selection**: ML-based model selection based on document characteristics
2. **Cost-Aware Fallback**: Consider cost when selecting fallback models
3. **Provider Health Monitoring**: Track provider reliability and adjust priorities
4. **Adaptive Timeouts**: Adjust timeouts based on model/provider performance
5. **Caching Layer**: Cache common completions to reduce API calls
