"""
LLM Usage Tracking Utilities

Shared utilities for tracking, aggregating, and logging LLM token usage across the codebase.
"""

import contextvars
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from litellm import ModelResponse

from src.core.config import config
from src.core.logging import get_logger

logger = get_logger(__name__)

# Module-level file handler and logger for LLM usage logging (dev only)
_usage_file_handler: logging.FileHandler | None = None
_usage_file_logger: logging.Logger | None = None

# Context variable for automatic usage tracking
# Automatically propagates through async/await boundaries
_usage_tracker: contextvars.ContextVar[Callable[[dict[str, Any]], None] | None] = (
    contextvars.ContextVar("usage_tracker", default=None)
)


@dataclass
class LLMUsageRecord:
    """Record of LLM token usage for a single operation."""

    operation: str
    model_name: str
    provider_model: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float | None = None


class UsageTracker:
    """
    Tracks LLM usage records and provides aggregation and logging utilities.

    Usage:
        tracker = UsageTracker()
        callback = tracker.create_tracker("my_operation")
        set_usage_tracker(callback)
        # ... make LLM calls ...
        summary, records = tracker.consume_summary()
        log_usage_summary(summary, records, context="my_context")
    """

    def __init__(self) -> None:
        """Initialize an empty usage tracker."""
        self.usage_records: list[LLMUsageRecord] = []

    def reset(self) -> None:
        """Clear all recorded usage statistics."""
        self.usage_records.clear()

    def create_tracker(self, operation: str) -> Callable[[dict[str, Any]], None]:
        """
        Create a usage tracking callback bound to a specific operation.

        Args:
            operation: Name of the operation being tracked (e.g., "detect_locale", "classify_document")

        Returns:
            Callback function that can be used with set_usage_tracker() or usage_tracking()
        """

        def callback(usage_data: dict[str, Any]) -> None:
            record = LLMUsageRecord(
                operation=operation,
                model_name=str(usage_data.get("model_name", "unknown")),
                provider_model=usage_data.get("provider_model"),
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                cost=usage_data.get("cost"),
            )
            self.usage_records.append(record)
            cost_str = f" cost=${record.cost:.6f}" if record.cost is not None else ""
            logger.debug(
                "LLM usage recorded: operation=%s model=%s provider=%s prompt=%s output=%s total=%s%s",
                record.operation,
                record.model_name,
                record.provider_model,
                record.prompt_tokens,
                record.completion_tokens,
                record.total_tokens,
                cost_str,
            )

        return callback

    def get_summary(self) -> dict[str, dict[str, Any]]:
        """
        Aggregate token usage by model without clearing records.

        Returns:
            Dictionary mapping model names to aggregated statistics:
            {
                "model_name":             {
                "prompt_tokens": int,
                "completion_tokens": int,
                "total_tokens": int,
                "cost": float,
                "provider_models": list[str]
            }
            }
        """
        summary: dict[str, dict[str, Any]] = {}
        for record in self.usage_records:
            entry = summary.setdefault(
                record.model_name,
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost": 0.0,
                    "provider_models": set(),
                },
            )
            entry["prompt_tokens"] += record.prompt_tokens
            entry["completion_tokens"] += record.completion_tokens
            entry["total_tokens"] += record.total_tokens
            if record.cost is not None:
                entry["cost"] = (entry.get("cost", 0.0) or 0.0) + record.cost
            if record.provider_model:
                entry["provider_models"].add(record.provider_model)

        # Convert sets to sorted lists for JSON serialization
        for entry in summary.values():
            providers = entry.get("provider_models")
            if isinstance(providers, set):
                entry["provider_models"] = sorted(providers)

        return summary

    def consume_summary(self) -> tuple[dict[str, dict[str, Any]], list[LLMUsageRecord]]:
        """
        Return aggregated usage information and clear recorded statistics.

        Returns:
            Tuple of (summary_dict, records_list). After calling, usage_records is cleared.
        """
        summary = self.get_summary()
        records = self.usage_records.copy()
        self.reset()
        return summary, records


def format_usage_summary(summary: dict[str, dict[str, Any]], include_providers: bool = True) -> str:
    """
    Format usage summary as a human-readable string.

    Args:
        summary: Usage summary dictionary from UsageTracker.get_summary()
        include_providers: Whether to include provider model information

    Returns:
        Formatted string like: "model1: prompt=100 output=50 total=150 cost=$0.001; model2: prompt=200 output=100 total=300 cost=$0.002"
    """
    summary_parts: list[str] = []
    for model, stats in summary.items():
        provider_str = ""
        if include_providers:
            providers = stats.get("provider_models") or []
            if providers:
                provider_str = f" [{', '.join(providers)}]"

        cost_str = ""
        cost = stats.get("cost")
        if cost is not None and cost > 0:
            cost_str = f" cost=${cost:.6f}"

        summary_parts.append(
            f"{model}{provider_str}: prompt={stats['prompt_tokens']} "
            f"output={stats['completion_tokens']} total={stats['total_tokens']}{cost_str}"
        )

    return "; ".join(summary_parts)


def _get_usage_file_logger() -> logging.Logger | None:
    """
    Get or create the file logger for LLM usage logging (dev only).

    Returns:
        Logger if in development mode, None otherwise
    """
    global _usage_file_handler, _usage_file_logger

    # Only create file logger in development mode
    if not config.app.is_development:
        return None

    # Return existing logger if already created
    if _usage_file_logger is not None:
        return _usage_file_logger

    try:
        # Ensure logs directory exists
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create file handler with append mode
        log_file_path = log_dir / "llm_usage.log"
        _usage_file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
        _usage_file_handler.setLevel(logging.DEBUG)

        # Use a simple format for file logging
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        _usage_file_handler.setFormatter(formatter)

        # Create logger that uses our file handler
        _usage_file_logger = logging.getLogger("llm_usage_file")
        _usage_file_logger.setLevel(logging.DEBUG)
        _usage_file_logger.addHandler(_usage_file_handler)
        # Prevent propagation to root logger
        _usage_file_logger.propagate = False

        logger.debug(f"📝 LLM usage file logging enabled: {log_file_path}")
        return _usage_file_logger
    except Exception as e:
        logger.warning(f"Failed to set up LLM usage file logging: {e}")
        return None


def _write_usage_to_file(
    summary: dict[str, dict[str, Any]],
    records: list[LLMUsageRecord],
    context: str | None = None,
    reason: str | None = None,
    operation_type: str | None = None,
    product_slug: str | None = None,
    product_id: str | None = None,
    document_url: str | None = None,
    document_title: str | None = None,
    document_id: str | None = None,
) -> None:
    """
    Write LLM usage summary to file with metadata (dev only).

    Args:
        summary: Usage summary dictionary
        records: List of usage records
        context: Context identifier
        reason: Optional reason suffix
        operation_type: Type of operation (e.g., "summarization", "crawl", "product_overview")
        product_slug: Product slug identifier
        product_id: Product ID identifier
        document_url: URL of the document being processed
        document_title: Title of the document
        document_id: ID of the document
    """
    file_logger = _get_usage_file_logger()
    if not file_logger:
        return

    try:
        # Build metadata dictionary
        metadata_parts: list[str] = []

        if operation_type:
            metadata_parts.append(f"operation={operation_type}")
        if product_slug:
            metadata_parts.append(f"product_slug={product_slug}")
        if product_id:
            metadata_parts.append(f"product_id={product_id}")
        if document_id:
            metadata_parts.append(f"document_id={document_id}")
        if document_url:
            metadata_parts.append(f"url={document_url}")
        if document_title:
            metadata_parts.append(f"title={document_title}")
        if reason:
            metadata_parts.append(f"reason={reason}")
        if context:
            metadata_parts.append(f"context={context}")

        metadata_str = " | ".join(metadata_parts) if metadata_parts else ""

        # Write summary line with metadata
        formatted_summary = format_usage_summary(summary, include_providers=False)
        if metadata_str:
            file_logger.info(f"LLM Usage | {metadata_str} | {formatted_summary}")
        else:
            file_logger.info(f"LLM Usage | {formatted_summary}")

        # Write detailed records with metadata
        for record in records:
            provider_str = f" [{record.provider_model}]" if record.provider_model else ""
            detail_metadata = f" | {metadata_str}" if metadata_str else ""
            file_logger.debug(
                f"LLM Detail | operation={record.operation} model={record.model_name}{provider_str} "
                f"prompt={record.prompt_tokens} output={record.completion_tokens} "
                f"total={record.total_tokens}{detail_metadata}"
            )
    except Exception as e:
        logger.warning(f"Failed to write LLM usage to file: {e}")


def log_usage_summary(
    summary: dict[str, dict[str, Any]],
    records: list[LLMUsageRecord],
    context: str | None = None,
    reason: str | None = None,
    log_level: str = "info",
    operation_type: str | None = None,
    product_slug: str | None = None,
    product_id: str | None = None,
    document_url: str | None = None,
    document_title: str | None = None,
    document_id: str | None = None,
) -> None:
    """
    Log LLM usage summary and detailed records.

    Args:
        summary: Usage summary dictionary from UsageTracker.get_summary()
        records: List of usage records
        context: Context identifier (e.g., URL, request ID, operation name)
        reason: Optional reason suffix for the log message
        log_level: Logging level ("info", "debug", "warning")
        operation_type: Type of operation (e.g., "summarization", "crawl", "product_overview", "classify_document")
        product_slug: Product slug identifier
        product_id: Product ID identifier
        document_url: URL of the document being processed
        document_title: Title of the document
        document_id: ID of the document
    """
    if not summary:
        if context:
            logger.debug(f"No LLM usage recorded for {context}")
        return

    reason_suffix = f" ({reason})" if reason else ""
    context_str = f" for {context}" if context else ""
    formatted_summary = format_usage_summary(summary)

    # Log summary at specified level
    log_func = getattr(logger, log_level, logger.info)
    log_func(f"🔢 LLM token usage{context_str}{reason_suffix}: {formatted_summary}")

    # Log detailed records at debug level
    for record in records:
        logger.debug(
            "LLM usage detail: context=%s operation=%s model=%s provider=%s prompt=%s output=%s total=%s",
            context or "unknown",
            record.operation,
            record.model_name,
            record.provider_model,
            record.prompt_tokens,
            record.completion_tokens,
            record.total_tokens,
        )

    # Write to file in dev mode with metadata
    _write_usage_to_file(
        summary,
        records,
        context,
        reason,
        operation_type,
        product_slug,
        product_id,
        document_url,
        document_title,
        document_id,
    )


def aggregate_usage_records(records: list[LLMUsageRecord]) -> dict[str, dict[str, Any]]:
    """
    Aggregate a list of usage records into a summary dictionary.

    Useful when you have records from multiple sources or want to aggregate
    without using UsageTracker.

    Args:
        records: List of LLMUsageRecord instances

    Returns:
        Aggregated summary dictionary (same format as UsageTracker.get_summary())
    """
    summary: dict[str, dict[str, Any]] = {}
    for record in records:
        entry = summary.setdefault(
            record.model_name,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost": 0.0,
                "provider_models": set(),
            },
        )
        entry["prompt_tokens"] += record.prompt_tokens
        entry["completion_tokens"] += record.completion_tokens
        entry["total_tokens"] += record.total_tokens
        if record.cost is not None:
            entry["cost"] = (entry.get("cost", 0.0) or 0.0) + record.cost
        if record.provider_model:
            entry["provider_models"].add(record.provider_model)

    # Convert sets to sorted lists
    for entry in summary.values():
        providers = entry.get("provider_models")
        if isinstance(providers, set):
            entry["provider_models"] = sorted(providers)

    return summary


def _get_usage_value(usage_obj: Any, keys: list[str]) -> int:
    """
    Safely extract an integer token count from a usage object or dictionary.
    """
    for key in keys:
        value: Any | None = None
        if isinstance(usage_obj, dict):
            value = usage_obj.get(key)
        else:
            value = getattr(usage_obj, key, None)

        if value is None:
            continue

        if isinstance(value, int | float):
            return int(value)

        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue

    return 0


def set_usage_tracker(callback: Callable[[dict[str, Any]], None] | None) -> None:
    """
    Set the usage tracker callback for the current async context.

    This callback will be automatically invoked for all LLM completions
    within this context. Works seamlessly with async/await boundaries.

    Args:
        callback: Function that receives usage data dict with keys:
                 model_name, provider_model, prompt_tokens, completion_tokens, total_tokens
    """
    _usage_tracker.set(callback)


def get_usage_tracker() -> Callable[[dict[str, Any]], None] | None:
    """
    Get the usage tracker callback from the current async context.

    Returns:
        The callback function if set, None otherwise
    """
    return _usage_tracker.get()


@asynccontextmanager
async def usage_tracking(callback: Callable[[dict[str, Any]], None]) -> Any:
    """
    Async context manager for automatic usage tracking.

    Sets up usage tracking for all LLM calls within the context.
    Automatically restores previous tracker when exiting.

    Example:
        async with usage_tracking(my_callback):
            response = await acompletion_with_fallback(messages=[...])
            # Usage automatically tracked
    """
    previous = get_usage_tracker()
    set_usage_tracker(callback)
    try:
        yield
    finally:
        set_usage_tracker(previous)


def track_usage(
    response: ModelResponse,
    model_name: str,
    provider_model: str,
    duration: float | None = None,
) -> None:
    """
    Extract usage data from response and invoke tracker from context if available.

    Args:
        response: ModelResponse from litellm
        model_name: The model name that was used
        provider_model: The actual provider model identifier
        duration: Optional duration in seconds for the completion
    """
    callback = get_usage_tracker()
    if not callback:
        return

    try:
        usage = getattr(response, "usage", None)
        prompt_tokens = (
            _get_usage_value(usage, ["prompt_tokens", "input_tokens", "tokens_input"])
            if usage
            else 0
        )
        completion_tokens = (
            _get_usage_value(usage, ["completion_tokens", "output_tokens", "tokens_output"])
            if usage
            else 0
        )
        total_tokens = (
            _get_usage_value(usage, ["total_tokens"])
            if usage
            else prompt_tokens + completion_tokens
        )
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens

        # Extract cost and timing from litellm response
        cost: float | None = None
        ttft: float | None = None

        try:
            hidden_params = getattr(response, "_hidden_params", None)
            if hidden_params and isinstance(hidden_params, dict):
                cost = hidden_params.get("response_cost")
                if cost is not None:
                    try:
                        cost = float(cost)
                    except (TypeError, ValueError):
                        cost = None

                # Try to extract TTFT from various possible locations
                ttft = hidden_params.get("ttft") or hidden_params.get("time_to_first_token")
                if ttft is not None:
                    try:
                        ttft = float(ttft)
                    except (TypeError, ValueError):
                        ttft = None

            # Also check response metadata/attributes for timing info
            if ttft is None:
                # Check for response_ms and convert to seconds
                response_ms = getattr(response, "response_ms", None)
                if response_ms is not None:
                    try:
                        # For non-streaming, TTFT is approximately the response time
                        ttft = float(response_ms) / 1000.0
                    except (TypeError, ValueError):
                        pass
        except Exception:
            # Cost and timing extraction is optional, don't fail if it's not available
            pass

        # For non-streaming responses, if TTFT not available, approximate with total duration
        if ttft is None and duration is not None:
            ttft = duration

        # Log completion details at debug level
        time_str = f"{duration:.3f}s" if duration is not None else "N/A"
        ttft_str = f" ttft={ttft:.3f}s" if ttft is not None else ""
        cost_str = f" ${cost:.6f}" if cost is not None and cost > 0 else ""
        logger.debug(
            f"LLM completion: model={model_name} time={time_str}{ttft_str} "
            f"input={prompt_tokens} output={completion_tokens} total={total_tokens}{cost_str}"
        )

        callback(
            {
                "model_name": model_name,
                "provider_model": provider_model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost": cost,
            }
        )
    except Exception as callback_error:  # pragma: no cover - defensive
        logger.exception("Usage callback failed for model %s: %s", model_name, callback_error)
