"""
LLM Usage Tracking Mixin

Base class mixin that provides LLM usage tracking capabilities to any class
that makes LLM calls. This allows consistent usage tracking across the codebase.
"""

from collections.abc import Callable
from typing import Any

from src.utils.llm_usage import LLMUsageRecord, UsageTracker, log_usage_summary


class LLMUsageTrackingMixin:
    """
    Mixin class that provides LLM usage tracking capabilities.

    Classes that make LLM calls can inherit from this mixin to get:
    - Usage tracker initialization
    - Methods to reset, get, and consume usage statistics
    - Helper method to create usage tracking callbacks

    Usage:
        class MyAnalyzer(LLMUsageTrackingMixin):
            def __init__(self):
                super().__init__()
                # ... other initialization ...

            async def analyze(self, text: str):
                async with usage_tracking(self._create_usage_tracker("analyze")):
                    response = await acompletion_with_fallback(...)
                    # Usage automatically tracked
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize the usage tracker.

        Subclasses should call super().__init__() in their __init__ methods.
        """
        # Call parent __init__ if it exists (for mixin pattern)
        # This works with Python's MRO - if no other parent, calls object.__init__
        # Note: type checker may complain, but this is correct for mixin pattern
        super().__init__(*args, **kwargs)
        self.usage_tracker = UsageTracker()

    def reset_usage_stats(self) -> None:
        """Clear recorded LLM usage statistics."""
        self.usage_tracker.reset()

    def _create_usage_tracker(self, operation: str) -> Callable[[dict[str, Any]], None]:
        """
        Create a usage tracking callback bound to a specific operation.

        Args:
            operation: Name of the operation being tracked (e.g., "detect_locale", "classify_document")

        Returns:
            Callback function that can be used with usage_tracking() context manager
        """
        callback: Callable[[dict[str, Any]], None] = self.usage_tracker.create_tracker(operation)
        return callback

    def get_usage_summary(self) -> dict[str, dict[str, Any]]:
        """
        Aggregate token usage by model without clearing records.

        Returns:
            Dictionary mapping model names to aggregated statistics:
            {
                "model_name": {
                    "prompt_tokens": int,
                    "completion_tokens": int,
                    "total_tokens": int,
                    "provider_models": list[str]
                }
            }
        """
        summary: dict[str, dict[str, Any]] = self.usage_tracker.get_summary()
        return summary

    def consume_usage_summary(self) -> tuple[dict[str, dict[str, Any]], list[LLMUsageRecord]]:
        """
        Return aggregated usage information and clear recorded statistics.

        Returns:
            Tuple of (summary_dict, records_list). After calling, usage_records is cleared.
        """
        summary: dict[str, dict[str, Any]]
        records: list[LLMUsageRecord]
        summary, records = self.usage_tracker.consume_summary()
        return summary, records

    def log_llm_usage(
        self,
        context: str,
        reason: str | None = None,
        operation_type: str | None = None,
        product_slug: str | None = None,
        product_id: str | None = None,
        document_url: str | None = None,
        document_title: str | None = None,
        document_id: str | None = None,
    ) -> None:
        """
        Consolidate and log token usage for LLM calls executed during processing.

        Args:
            context: Context identifier (e.g., URL, request ID, operation name)
            reason: Optional reason suffix for the log message
            operation_type: Type of operation (e.g., "summarization", "crawl", "classify_document")
            product_slug: Product slug identifier
            product_id: Product ID identifier
            document_url: URL of the document being processed
            document_title: Title of the document
            document_id: ID of the document
        """
        summary, records = self.consume_usage_summary()
        log_usage_summary(
            summary,
            records,
            context=context,
            reason=reason,
            operation_type=operation_type,
            product_slug=product_slug,
            product_id=product_id,
            document_url=document_url,
            document_title=document_title,
            document_id=document_id,
        )
