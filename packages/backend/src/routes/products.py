"""Product routes using Repository pattern with context manager."""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr

from src.core.database import get_db
from src.core.logging import get_logger
from src.models.document import (
    DocumentDeepAnalysis,
    DocumentExtraction,
    DocumentSummary,
    ProductAnalysis,
    ProductDeepAnalysis,
    ProductOverview,
)
from src.models.product import Product
from src.models.user import UserTier
from src.services.extraction_service import extract_document_facts
from src.services.service_factory import (
    create_indexation_notification_service,
    create_product_service,
    create_services,
    create_user_service,
)
from src.summarizer import (
    generate_document_deep_analysis,
    generate_product_deep_analysis,
    generate_product_overview,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


class IndexationNotifyRequest(BaseModel):
    email: EmailStr


def _get_user_id(request: Request) -> str | None:
    """Extract user_id from request state (set by auth middleware)."""
    user = getattr(request.state, "user", None)
    if user and isinstance(user, dict):
        return user.get("user_id")
    return None


async def _require_pro_tier(db, request: Request) -> None:
    user_id = _get_user_id(request)
    if user_id in (None, "localhost_dev", "service_account"):
        return
    user_service = create_user_service()
    user = await user_service.get_user_by_id(db, user_id)
    if not user or user.tier != UserTier.PRO:
        raise HTTPException(
            status_code=402,
            detail="This feature requires a Pro subscription.",
        )


@router.get("", response_model=list[Product])
async def get_all_products(
    include_all: bool = Query(
        default=False,
        description="If true, returns all products. If false (default), returns only products with at least one document.",
    ),
) -> list[Product]:
    """Get a list of products.

    By default, only returns products that have at least one document.
    Set include_all=true to get all products regardless of document count.
    """
    async with get_db() as db:
        service = create_product_service()
        if include_all:
            products = await service.get_all_products(db)
        else:
            products = await service.get_products_with_documents(db)
        return products


@router.get("/{slug}/overview", response_model=ProductOverview)
async def get_product_overview(slug: str, _request: Request) -> ProductOverview:
    """Get a quick decision-making overview for a product (Level 1).

    Note: This endpoint does NOT trigger generation. Overviews are expected
    to be produced by the indexation pipeline.
    """
    async with get_db() as db:
        service = create_product_service()

        product = await service.get_product_by_slug(db, slug)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        overview = await service.get_product_overview(db, slug)
        if overview:
            return overview

        raise HTTPException(
            status_code=404,
            detail={
                "message": "Overview not available yet. Indexation may be in progress.",
                "code": "overview_not_ready",
                "product_slug": slug,
            },
        )


@router.get("/{slug}/analysis", response_model=ProductAnalysis)
async def get_product_analysis(slug: str) -> ProductAnalysis:
    """Get a comprehensive analysis for a product (Level 2).
    Generates the analysis on-the-fly if it doesn't exist yet.
    """
    async with get_db() as db:
        service = create_product_service()

        # First check if product exists
        product = await service.get_product_by_slug(db, slug)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Try to get existing analysis
        analysis = await service.get_product_analysis(db, slug)
        if analysis:
            return analysis

        # Analysis doesn't exist - generate product overview JIT (which creates both overview and analysis)
        logger.info(f"Analysis not found for {slug}, generating on-the-fly...")
        try:
            product_svc, doc_svc = create_services()
            await generate_product_overview(db, slug, product_svc=product_svc, document_svc=doc_svc)
            # Now get the analysis (it should exist after generation)
            analysis = await service.get_product_analysis(db, slug)
            if analysis:
                return analysis
            else:
                # This shouldn't happen, but handle it gracefully
                logger.error(f"Failed to retrieve analysis after generation for {slug}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to generate product analysis. Please try again later.",
                )
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Error generating analysis for {slug}: {e}")
            raise HTTPException(
                status_code=404,
                detail="Product analysis not available. The product exists but has no documents to analyze yet.",
            ) from e


@router.get("/{slug}/documents", response_model=list[DocumentSummary])
async def get_product_documents(slug: str) -> list[DocumentSummary]:
    """Get a list of analyzed documents for a product."""
    async with get_db() as db:
        service = create_product_service()
        documents = await service.get_product_documents(db, slug)
        return documents


@router.get("/{slug}/documents/{document_id}/extraction", response_model=DocumentExtraction)
async def get_document_extraction(
    slug: str,
    document_id: str,
    force_regenerate: bool = Query(
        default=False,
        description="If true, regenerates extraction even if cached by content hash.",
    ),
) -> DocumentExtraction:
    """Get evidence-backed extraction for a specific document (auditability).

    If missing or stale, this will generate extraction and persist it on the Document.
    """
    async with get_db() as db:
        product_svc, doc_svc = create_services()

        product = await product_svc.get_product_by_slug(db, slug)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        doc = await doc_svc.get_document_by_id(db, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.product_id != product.id:
            raise HTTPException(status_code=404, detail="Document not found for this product")

        # Ensure extraction exists and is up-to-date
        extraction = doc.extraction
        if force_regenerate:
            extraction = None

        if extraction is None:
            try:
                extraction = await extract_document_facts(doc, use_cache=not force_regenerate)
                doc.extraction = extraction
                await doc_svc.update_document(db, doc)
            except Exception as e:
                logger.error(f"Error generating extraction for {document_id}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to generate document extraction. Please try again later.",
                ) from e

        return extraction


@router.get("/{slug}/deep-analysis", response_model=ProductDeepAnalysis)
async def get_product_deep_analysis_route(slug: str, request: Request) -> ProductDeepAnalysis:
    """Get deep analysis for a product (Level 3).
    Generates the deep analysis on-the-fly if it doesn't exist yet.
    """
    async with get_db() as db:
        await _require_pro_tier(db, request)
        service = create_product_service()

        # First check if product exists
        product = await service.get_product_by_slug(db, slug)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Try to get existing deep analysis
        deep_analysis = await service.get_product_deep_analysis(db, slug)
        if deep_analysis:
            return deep_analysis

        # Deep analysis doesn't exist - generate it JIT
        logger.info(f"Deep analysis not found for {slug}, generating on-the-fly...")
        try:
            product_svc, doc_svc = create_services()
            deep_analysis = await generate_product_deep_analysis(
                db, slug, product_svc=product_svc, document_svc=doc_svc
            )
            return deep_analysis
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Error generating deep analysis for {slug}: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to generate product deep analysis. Please try again later.",
            ) from e


@router.get(
    "/{slug}/documents/{document_id}/deep-analysis",
    response_model=DocumentDeepAnalysis,
)
async def get_document_deep_analysis_route(
    slug: str, document_id: str, request: Request
) -> DocumentDeepAnalysis:
    """Get deep analysis for a single document (paid)."""
    async with get_db() as db:
        await _require_pro_tier(db, request)
        product_svc, doc_svc = create_services()

        product = await product_svc.get_product_by_slug(db, slug)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        doc = await doc_svc.get_document_by_id(db, document_id)
        if not doc or doc.product_id != product.id:
            raise HTTPException(status_code=404, detail="Document not found")

        try:
            return await generate_document_deep_analysis(db, doc, doc_svc)
        except Exception as e:
            logger.error(f"Error generating document deep analysis for {document_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to generate document deep analysis. Please try again later.",
            ) from e


@router.get("/{slug}", response_model=Product)
async def get_product_by_slug(slug: str) -> Product:
    """Get a product by its slug."""
    async with get_db() as db:
        service = create_product_service()
        product = await service.get_product_by_slug(db, slug)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return product


@router.post("/{slug}/indexation-notify")
async def subscribe_indexation_notify(
    slug: str, payload: IndexationNotifyRequest
) -> dict[str, str]:
    """Subscribe an email to be notified when indexation completes for a product."""
    async with get_db() as db:
        product_svc = create_product_service()
        product = await product_svc.get_product_by_slug(db, slug)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        svc = create_indexation_notification_service()
        await svc.subscribe(db, product_slug=slug, email=str(payload.email))
        return {"status": "ok"}
