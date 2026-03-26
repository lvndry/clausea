"""Product routes using Repository pattern with Depends."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from motor.core import AgnosticDatabase
from pydantic import BaseModel, EmailStr
from starlette.status import HTTP_404_NOT_FOUND, HTTP_424_FAILED_DEPENDENCY, HTTP_425_TOO_EARLY

from src.core.database import get_db
from src.core.logging import get_logger
from src.core.tier_deps import check_usage_limit, get_user_tier, increment_usage
from src.models.document import (
    CORE_DOC_TYPES,
    DocumentDeepAnalysis,
    DocumentExtraction,
    DocumentSummary,
    ProductAnalysis,
    ProductDeepAnalysis,
    ProductOverview,
)
from src.models.product import Product
from src.models.user import UserTier
from src.services.document_service import DocumentService
from src.services.extraction_service import extract_document_facts
from src.services.product_service import ProductService
from src.services.service_factory import (
    create_indexation_notification_service,
    create_product_service,
    create_services,
)
from src.summarizer import (
    generate_document_deep_analysis,
    generate_product_deep_analysis,
    generate_product_overview,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


def _can_access_document(
    *, tier: UserTier, doc_type: str | None, tier_relevance: str | None
) -> bool:
    """Free users can access core docs only; Pro can access all docs."""
    if tier == UserTier.PRO:
        return True
    if tier_relevance == "core":
        return True
    return bool(doc_type and doc_type in CORE_DOC_TYPES)


def get_product_and_document_services() -> tuple[ProductService, DocumentService]:
    """Dependency that returns both product and document services with shared repos."""

    product_svc, doc_svc = create_services()
    return (product_svc, doc_svc)


class IndexationNotifyRequest(BaseModel):
    email: EmailStr


@router.get("", response_model=list[Product])
async def get_all_products(
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
    include_all: bool = Query(
        default=False,
        description="If true, returns all products. If false (default), returns only products with at least one document.",
    ),
) -> list[Product]:
    """Get a list of products.

    By default, only returns products that have at least one document.
    Set include_all=true to get all products regardless of document count.
    """
    if include_all:
        return await service.get_all_products(db)
    return await service.get_products_with_documents(db)


@router.get("/{slug}/overview", response_model=ProductOverview)
async def get_product_overview(
    slug: str,
    _request: Request,
    _usage: None = Depends(check_usage_limit),
    _increment: None = Depends(increment_usage),
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
) -> ProductOverview:
    """Get a quick decision-making overview for a product (Level 1).

    Note: This endpoint does NOT trigger generation. Overviews are expected
    to be produced by the indexation pipeline.

    Status codes:
        404: No product with this slug.
        425: Product exists but overview is not available yet (indexation in progress).
    """
    product = await service.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Product not found")

    overview = await service.get_product_overview(db, slug)
    if overview:
        return overview

    raise HTTPException(
        status_code=HTTP_425_TOO_EARLY,
        detail={
            "message": "Overview not available yet. Indexation may be in progress.",
            "code": "overview_not_ready",
            "product_slug": slug,
        },
    )


@router.get("/{slug}/analysis", response_model=ProductAnalysis)
async def get_product_analysis(
    slug: str,
    _usage: None = Depends(check_usage_limit),
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
    services: tuple[ProductService, DocumentService] = Depends(get_product_and_document_services),
) -> ProductAnalysis:
    """Get a comprehensive analysis for a product (Level 2).
    Generates the analysis on-the-fly if it doesn't exist yet.
    """
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
        product_svc, doc_svc = services
        await generate_product_overview(db, slug, product_svc=product_svc, document_svc=doc_svc)
        # Now get the analysis (it should exist after generation)
        analysis = await service.get_product_analysis(db, slug)
        if analysis:
            return analysis
        # This shouldn't happen, but handle it gracefully
        logger.error(f"Failed to retrieve analysis after generation for {slug}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate product analysis. Please try again later.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating analysis for {slug}: {e}")
        raise HTTPException(
            status_code=HTTP_424_FAILED_DEPENDENCY,
            detail="Product analysis not available. The product exists but has no documents to analyze yet.",
        ) from e


@router.get("/{slug}/documents", response_model=list[DocumentSummary])
async def get_product_documents(
    slug: str,
    user_tier: UserTier = Depends(get_user_tier),
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
) -> list[DocumentSummary]:
    """Get a list of analyzed documents for a product.

    Status codes:
        404: No product with this slug.
        200: Product exists; body may be an empty list when indexation found no documents yet.
    """
    product = await service.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Product not found")
    docs = await service.get_product_documents(db, slug)
    if user_tier == UserTier.PRO:
        return docs
    return [
        doc
        for doc in docs
        if _can_access_document(tier=user_tier, doc_type=doc.doc_type, tier_relevance=None)
    ]


@router.get("/{slug}/documents/{document_id}/extraction", response_model=DocumentExtraction)
async def get_document_extraction(
    slug: str,
    document_id: str,
    user_tier: UserTier = Depends(get_user_tier),
    db: AgnosticDatabase = Depends(get_db),
    services: tuple[ProductService, DocumentService] = Depends(get_product_and_document_services),
    force_regenerate: bool = Query(
        default=False,
        description="If true, regenerates extraction even if cached by content hash.",
    ),
) -> DocumentExtraction:
    """Get evidence-backed extraction for a specific document (auditability).

    If missing or stale, this will generate extraction and persist it on the Document.
    """
    product_svc, doc_svc = services

    product = await product_svc.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    doc = await doc_svc.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.product_id != product.id:
        raise HTTPException(status_code=404, detail="Document not found for this product")
    if not _can_access_document(
        tier=user_tier,
        doc_type=doc.doc_type,
        tier_relevance=doc.tier_relevance,
    ):
        raise HTTPException(status_code=402, detail="Upgrade to Pro to access this document.")

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
async def get_product_deep_analysis_route(
    slug: str,
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
    services: tuple[ProductService, DocumentService] = Depends(get_product_and_document_services),
) -> ProductDeepAnalysis:
    """Get deep analysis for a product (Level 3).
    Generates the deep analysis on-the-fly if it doesn't exist yet.
    """
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
        product_svc, doc_svc = services
        return await generate_product_deep_analysis(
            db, slug, product_svc=product_svc, document_svc=doc_svc
        )
    except HTTPException:
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
    slug: str,
    document_id: str,
    user_tier: UserTier = Depends(get_user_tier),
    db: AgnosticDatabase = Depends(get_db),
    services: tuple[ProductService, DocumentService] = Depends(get_product_and_document_services),
) -> DocumentDeepAnalysis:
    """Get deep analysis for a single document (paid)."""
    product_svc, doc_svc = services

    product = await product_svc.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    doc = await doc_svc.get_document_by_id(db, document_id)
    if not doc or doc.product_id != product.id:
        raise HTTPException(status_code=404, detail="Document not found")
    if not _can_access_document(
        tier=user_tier,
        doc_type=doc.doc_type,
        tier_relevance=doc.tier_relevance,
    ):
        raise HTTPException(status_code=402, detail="Upgrade to Pro to access this document.")

    try:
        return await generate_document_deep_analysis(db, doc, doc_svc)
    except Exception as e:
        logger.error(f"Error generating document deep analysis for {document_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate document deep analysis. Please try again later.",
        ) from e


@router.get("/{slug}", response_model=Product)
async def get_product_by_slug(
    slug: str,
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
) -> Product:
    """Get a product by its slug.

    Returns 404 only when no product exists for this slug (not when documents or overview are missing).
    """
    product = await service.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post("/{slug}/indexation-notify", status_code=201)
async def subscribe_indexation_notify(
    slug: str,
    payload: IndexationNotifyRequest,
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
) -> dict[str, str]:
    """Subscribe an email to be notified when indexation completes for a product."""
    product = await service.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    svc = create_indexation_notification_service()
    await svc.subscribe(db, product_slug=slug, email=str(payload.email))
    return {"status": "ok"}
