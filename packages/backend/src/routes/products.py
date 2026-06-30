"""Product routes using Repository pattern with Depends."""

from __future__ import annotations

from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from motor.core import AgnosticDatabase
from pydantic import BaseModel, EmailStr
from starlette.status import HTTP_404_NOT_FOUND, HTTP_424_FAILED_DEPENDENCY, HTTP_425_TOO_EARLY

from src.analyser import (
    generate_document_deep_analysis,
    generate_product_overview,
)
from src.core.database import get_db
from src.core.logging import get_logger
from src.core.tier_deps import check_usage_limit, get_user_tier, increment_usage, require_pro
from src.models.document import (
    CORE_DOC_TYPES,
    ConsumerExplainer,
    DocumentDeepAnalysis,
    DocumentExtraction,
    DocumentSummary,
    ProductAnalysis,
    ProductDeepAnalysis,
    ProductOverview,
)
from src.models.pipeline_job import PipelineErrorCode
from src.models.product import Product
from src.models.topic_report import ProductTopicReport
from src.models.user import UserTier
from src.repositories.document_repository import DocumentRepository
from src.repositories.product_intelligence_repository import ProductIntelligenceRepository
from src.services.document_service import DocumentService
from src.services.extraction_service import extract_document_facts
from src.services.product_service import ProductService
from src.services.rollup_hydration import rollup_to_hydrated
from src.services.service_factory import (
    create_indexation_notification_service,
    create_product_service,
    create_services,
)
from src.services.thin_evidence_gate import ThinEvidenceSkipped
from src.services.topic_report_service import build_product_topic_report

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


class ProductsPage(BaseModel):
    items: list[Product]
    total: int
    page: int
    pages: int


@router.get("", response_model=ProductsPage)
async def get_all_products(
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str = Query(default=""),
) -> ProductsPage:
    """Get a paginated list of products with optional search."""
    products, total = await service.get_products_paginated(
        db, page=page, limit=limit, search=search
    )
    pages = ceil(total / limit) if total > 0 else 1
    return ProductsPage(items=products, total=total, page=page, pages=pages)


class ProductStats(BaseModel):
    analyzed_count: int


@router.get("/stats", response_model=ProductStats)
async def get_product_stats(
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
) -> ProductStats:
    """Public catalog stats for the landing page (count of analyzed products)."""
    return ProductStats(analyzed_count=await service.count_analyzed_products(db))


class SitemapEntry(BaseModel):
    slug: str
    last_modified: datetime | None = None


@router.get("/sitemap", response_model=list[SitemapEntry])
async def get_products_sitemap(
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
) -> list[SitemapEntry]:
    """Analyzed products (slug + last update) for the public sitemap."""
    rows = await service.list_analyzed_products_for_sitemap(db)
    return [
        SitemapEntry(slug=row["product_slug"], last_modified=row.get("updated_at"))
        for row in rows
        if row.get("product_slug")
    ]


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

    # Load intelligence once with a targeted projection (overview + compliance fields only,
    # no rollup/topic_report/explainer).  Passing it to get_product_overview avoids two more
    # full document fetches that previously happened inside product_repo.get_product_overview
    # and product_repo.get_product_compliance.
    intelligence = await ProductIntelligenceRepository().get_for_overview(db, product_id=product.id)
    if intelligence and intelligence.thin_evidence:
        raise HTTPException(
            status_code=HTTP_424_FAILED_DEPENDENCY,
            detail={
                "message": "Not enough policy documents were found to produce a reliable analysis.",
                "code": PipelineErrorCode.thin_evidence,
                "reason": intelligence.thin_evidence_reason,
            },
        )

    overview = await service.get_product_overview(
        db, slug, product=product, intelligence=intelligence
    )
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


@router.get("/{slug}/topics", response_model=ProductTopicReport)
async def get_product_topics(
    slug: str,
    _request: Request,
    _usage: None = Depends(check_usage_limit),
    _increment: None = Depends(increment_usage),
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
) -> ProductTopicReport:
    """Get per-topic cross-document findings with evidence citations."""
    product = await service.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Product not found")

    intel_repo = ProductIntelligenceRepository()
    cached_report = await intel_repo.get_topic_report_cached(db, product.id)
    if cached_report is not None:
        return cached_report

    intelligence = await intel_repo.get_rollup_for_topics(db, product.id)
    if not intelligence or not intelligence.rollup:
        raise HTTPException(
            status_code=HTTP_425_TOO_EARLY,
            detail={
                "message": "Topic findings are not available yet. Indexation may be in progress.",
                "code": "topics_not_ready",
                "product_slug": slug,
            },
        )

    doc_repo = DocumentRepository()
    referenced_ids = {
        doc_id for item in intelligence.rollup.items for doc_id in item.document_ids
    } | {doc_id for conflict in intelligence.rollup.conflicts for doc_id in conflict.document_ids}
    documents_for_hydration = await doc_repo.find_by_ids_with_extraction(
        db, product.id, sorted(referenced_ids)
    )
    hydrated_rollup = rollup_to_hydrated(
        product_id=product.id,
        product_slug=slug,
        rollup=intelligence.rollup,
        documents=documents_for_hydration,
    )

    documents = await service.get_product_documents(db, slug)
    report = build_product_topic_report(
        product_slug=slug,
        rollup=hydrated_rollup,
        documents=documents,
    )

    try:
        await ProductIntelligenceRepository().store_topic_report(db, product.id, report)
    except Exception as exc:
        logger.warning("Failed to store cached topic report for %s: %s", product.id, exc)

    return report


@router.get("/{slug}/explainer", response_model=ConsumerExplainer)
async def get_product_explainer(
    slug: str,
    _request: Request,
    _usage: None = Depends(check_usage_limit),
    _increment: None = Depends(increment_usage),
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
) -> ConsumerExplainer:
    """Get the plain-English consumer TOS-explainer for a product (the consumer-facing
    output). Does NOT trigger generation — produced by the indexation pipeline.
    Grade values are reconciled server-side to the canonical product overview score.

    Status codes:
        404: No product with this slug.
        425: Product exists but the explainer is not available yet.
    """
    product = await service.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Product not found")

    data = await service.get_product_explainer(db, slug)
    if data:
        return ConsumerExplainer.model_validate(data)

    raise HTTPException(
        status_code=HTTP_425_TOO_EARLY,
        detail={
            "message": "Explainer not available yet. Indexation may be in progress.",
            "code": "explainer_not_ready",
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
    except ThinEvidenceSkipped as thin_exc:
        logger.info("Analysis unavailable for %s due to thin evidence: %s", slug, thin_exc.reason)
        raise HTTPException(
            status_code=HTTP_424_FAILED_DEPENDENCY,
            detail={
                "message": "Not enough policy documents were found to produce a reliable analysis.",
                "code": PipelineErrorCode.thin_evidence,
                "reason": thin_exc.reason,
            },
        ) from thin_exc
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
    _usage: None = Depends(check_usage_limit),
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
    if not doc.is_linked_to_product(product.id):
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
    _: None = Depends(require_pro),
) -> ProductDeepAnalysis:
    """Get professional-grade compliance audit for a product (Level 3). Requires Pro subscription."""
    product = await service.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Return cached analysis only — JIT generation disabled until feature is shipped.
    deep_analysis = await service.get_product_deep_analysis(db, slug)
    if deep_analysis:
        return deep_analysis

    raise HTTPException(status_code=501, detail="Deep analysis is not yet available.")


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
    if not doc or not doc.is_linked_to_product(product.id):
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
    _usage: None = Depends(check_usage_limit),
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
) -> Product:
    """Get a product by its slug.

    Returns 404 only when no product exists for this slug (not when documents or overview are missing).
    """
    product = await service.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Product not found")

    # Use a 3-field projection — avoids loading the full intelligence document
    # (rollup, topic_report, explainer) just to check a single boolean.
    intelligence = await ProductIntelligenceRepository().get_thin_evidence_flags(db, product.id)
    if intelligence and intelligence.thin_evidence:
        product.thin_evidence = True
        product.thin_evidence_reason = intelligence.thin_evidence_reason
        product.indexation_error = intelligence.indexation_error or PipelineErrorCode.thin_evidence

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
