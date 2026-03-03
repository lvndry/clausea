from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.logging import get_logger
from src.services import promotion_service

logger = get_logger(__name__)

router = APIRouter(prefix="/promotion", tags=["promotion"])


class PromotionRequest(BaseModel):
    dry_run: bool = True


class PromotionResponse(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] | None = None
    error: str | None = None


@router.get("/summary", response_model=PromotionResponse)
async def get_promotion_summary() -> PromotionResponse:
    """Get a summary of what would be promoted from local to production."""
    try:
        summary = await promotion_service.get_summary()
        return PromotionResponse(
            success=True,
            message="Promotion summary retrieved successfully",
            data=summary,
        )
    except Exception as e:
        logger.exception("Error getting promotion summary", error=str(e))
        raise HTTPException(
            status_code=500, detail="Unable to fetch promotion summary. Please try again later."
        ) from e


@router.post("/dry-run", response_model=PromotionResponse)
async def run_dry_promotion() -> PromotionResponse:
    """Run a dry run promotion to see what would be promoted without actually promoting."""
    try:
        result = await promotion_service.run_dry_run()

        return PromotionResponse(
            success=True,
            message="Dry run promotion completed successfully",
            data=result,
        )
    except Exception as e:
        logger.exception("Error in dry run promotion", error=str(e))
        raise HTTPException(
            status_code=500, detail="Unable to run dry promotion. Please try again later."
        ) from e


@router.post("/execute", response_model=PromotionResponse)
async def execute_promotion(request: PromotionRequest) -> PromotionResponse:
    """Execute the actual promotion from local to production."""
    try:
        result = await promotion_service.execute(dry_run=request.dry_run)

        action = "dry run" if request.dry_run else "actual"
        return PromotionResponse(
            success=True,
            message=f"{action.capitalize()} promotion completed successfully",
            data=result,
        )
    except Exception as e:
        logger.exception("Error in promotion execution", error=str(e))
        raise HTTPException(
            status_code=500, detail="Unable to run promotion. Please try again later."
        ) from e


@router.post("/promote-products", response_model=PromotionResponse)
async def promote_products_only(request: PromotionRequest) -> PromotionResponse:
    """Promote only products from local to production."""
    try:
        result = await promotion_service.promote_products(dry_run=request.dry_run)

        action = "dry run" if request.dry_run else "actual"
        return PromotionResponse(
            success=True,
            message=f"Products {action} promotion completed successfully",
            data=result,
        )
    except Exception as e:
        logger.exception("Error in products promotion", error=str(e))
        raise HTTPException(
            status_code=500, detail="Unable to promote products. Please try again later."
        ) from e


@router.post("/promote-documents", response_model=PromotionResponse)
async def promote_documents_only(request: PromotionRequest) -> PromotionResponse:
    """Promote only documents from local to production."""
    try:
        result = await promotion_service.promote_documents(dry_run=request.dry_run)

        action = "dry run" if request.dry_run else "actual"
        return PromotionResponse(
            success=True,
            message=f"Documents {action} promotion completed successfully",
            data=result,
        )
    except Exception as e:
        logger.exception("Error in documents promotion", error=str(e))
        raise HTTPException(
            status_code=500, detail="Unable to promote documents. Please try again later."
        ) from e


@router.post("/promote-product-overviews", response_model=PromotionResponse)
async def promote_product_overviews_only(request: PromotionRequest) -> PromotionResponse:
    """Promote only product overviews from local to production."""
    try:
        result = await promotion_service.promote_product_overviews(dry_run=request.dry_run)

        action = "dry run" if request.dry_run else "actual"
        return PromotionResponse(
            success=True,
            message=f"Product overviews {action} promotion completed successfully",
            data=result,
        )
    except Exception as e:
        logger.exception("Error in product overviews promotion", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Unable to promote product overviews. Please try again later.",
        ) from e


@router.post("/promote-users-to-tier-system", response_model=PromotionResponse)
async def promote_users_to_tier_system_only(request: PromotionRequest) -> PromotionResponse:
    """Promote existing users to include tier and monthly_usage fields."""
    try:
        result = await promotion_service.promote_users_to_tier_system(dry_run=request.dry_run)

        action = "dry run" if request.dry_run else "actual"
        return PromotionResponse(
            success=True,
            message=f"User tier system {action} promotion completed successfully",
            data=result,
        )
    except Exception as e:
        logger.exception("Error in user tier promotion", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Unable to promote users to tier system. Please try again later.",
        ) from e


# Download endpoints (production -> local)


@router.post("/download", response_model=PromotionResponse)
async def download_all(request: PromotionRequest) -> PromotionResponse:
    """Download all data from production to local."""
    try:
        result = await promotion_service.download_all(dry_run=request.dry_run)

        action = "dry run" if request.dry_run else "actual"
        return PromotionResponse(
            success=True,
            message=f"{action.capitalize()} download completed successfully",
            data=result,
        )
    except Exception as e:
        logger.exception("Error in download execution", error=str(e))
        raise HTTPException(
            status_code=500, detail="Unable to download data. Please try again later."
        ) from e


@router.post("/download-products", response_model=PromotionResponse)
async def download_products_only(request: PromotionRequest) -> PromotionResponse:
    """Download only products from production to local."""
    try:
        result = await promotion_service.download_products(dry_run=request.dry_run)

        action = "dry run" if request.dry_run else "actual"
        return PromotionResponse(
            success=True,
            message=f"Products {action} download completed successfully",
            data=result,
        )
    except Exception as e:
        logger.exception("Error in products download", error=str(e))
        raise HTTPException(
            status_code=500, detail="Unable to download products. Please try again later."
        ) from e


@router.post("/download-documents", response_model=PromotionResponse)
async def download_documents_only(request: PromotionRequest) -> PromotionResponse:
    """Download only documents from production to local."""
    try:
        result = await promotion_service.download_documents(dry_run=request.dry_run)

        action = "dry run" if request.dry_run else "actual"
        return PromotionResponse(
            success=True,
            message=f"Documents {action} download completed successfully",
            data=result,
        )
    except Exception as e:
        logger.exception("Error in documents download", error=str(e))
        raise HTTPException(
            status_code=500, detail="Unable to download documents. Please try again later."
        ) from e


@router.post("/download-product-overviews", response_model=PromotionResponse)
async def download_product_overviews_only(request: PromotionRequest) -> PromotionResponse:
    """Download only product overviews from production to local."""
    try:
        result = await promotion_service.download_product_overviews(dry_run=request.dry_run)

        action = "dry run" if request.dry_run else "actual"
        return PromotionResponse(
            success=True,
            message=f"Product overviews {action} download completed successfully",
            data=result,
        )
    except Exception as e:
        logger.exception("Error in product overviews download", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Unable to download product overviews. Please try again later.",
        ) from e
