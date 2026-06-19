"""Pydantic models for the pipeline package."""

from typing import Any

from pydantic import BaseModel, Field


class ProcessingStats(BaseModel):
    products_processed: int = 0
    products_failed: int = 0
    failed_product_slugs: list[str] = Field(default_factory=list)
    total_urls_crawled: int = 0
    total_documents_found: int = 0
    policy_documents_processed: int = 0
    policy_documents_stored: int = 0
    english_documents: int = 0
    non_english_skipped: int = 0
    duplicates_skipped: int = 0
    processing_time_seconds: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0

    crawl_errors: list[dict[str, Any]] = Field(default_factory=list)
    crawl_skip_reasons: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = self.products_processed + self.products_failed
        return (self.products_processed / total * 100) if total > 0 else 0.0

    @property
    def legal_detection_rate(self) -> float:
        return (
            (self.policy_documents_processed / self.total_documents_found * 100)
            if self.total_documents_found > 0
            else 0.0
        )


__all__ = ["ProcessingStats"]
