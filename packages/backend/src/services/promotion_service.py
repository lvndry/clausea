from __future__ import annotations

from typing import Any

from src.core.logging import get_logger
from src.promotion import PromotionManager

logger = get_logger(__name__)


async def get_summary() -> dict[str, Any]:
    """Get a summary of the promotion process."""
    promotion_manager = PromotionManager()
    await promotion_manager.connect_databases()
    summary: dict[str, Any] = await promotion_manager.get_promotion_summary()
    await promotion_manager.close_connections()
    return summary


async def run_dry_run() -> dict[str, Any]:
    """Run a dry run of the promotion process."""
    promotion_manager = PromotionManager()
    result: dict[str, Any] = await promotion_manager.run_full_promotion(dry_run=True)
    return result


async def execute(dry_run: bool) -> dict[str, Any] | None:
    """Execute the promotion process."""
    promotion_manager = PromotionManager()
    result: dict[str, Any] = await promotion_manager.run_full_promotion(dry_run=dry_run)
    return result


async def promote_products(dry_run: bool) -> dict[str, Any]:
    """Promote products."""
    promotion_manager = PromotionManager()
    await promotion_manager.connect_databases()
    result: dict[str, Any] = await promotion_manager.promote_products(dry_run=dry_run)
    await promotion_manager.close_connections()
    return result


async def promote_documents(dry_run: bool) -> dict[str, Any]:
    """Promote documents."""
    promotion_manager = PromotionManager()
    await promotion_manager.connect_databases()
    result: dict[str, Any] = await promotion_manager.promote_documents(dry_run=dry_run)
    await promotion_manager.close_connections()
    return result


async def promote_product_overviews(dry_run: bool) -> dict[str, Any]:
    """Promote product overviews."""
    promotion_manager = PromotionManager()
    await promotion_manager.connect_databases()
    result: dict[str, Any] = await promotion_manager.promote_product_overviews(dry_run=dry_run)
    await promotion_manager.close_connections()
    return result


async def promote_users_to_tier_system(dry_run: bool) -> dict[str, Any]:
    """Promote existing users to include tier and monthly_usage fields"""
    promotion_manager = PromotionManager()
    await promotion_manager.connect_databases()
    result: dict[str, Any] = await promotion_manager.promote_users_to_tier_system(dry_run=dry_run)
    await promotion_manager.close_connections()
    return result
