from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from motor.core import AgnosticDatabase
from pydantic import BaseModel
from starlette.status import HTTP_404_NOT_FOUND

from src.core.database import get_db
from src.core.tier_deps import check_usage_limit, increment_usage
from src.models.product_intelligence import OverviewSnapshot
from src.repositories.document_change_repository import DocumentChangeRepository
from src.repositories.document_repository import DocumentRepository
from src.repositories.product_intelligence_repository import ProductIntelligenceRepository
from src.services.product_service import ProductService
from src.services.service_factory import create_product_service

router = APIRouter(prefix="/history", tags=["history"])


class DocumentChangeSummary(BaseModel):
    id: str
    created_at: datetime
    changed_fields: list[str]
    job_id: str | None
    content_hash: str
    previous_hash: str | None


@router.get("/documents/{document_id}/changes", response_model=list[DocumentChangeSummary])
async def list_document_changes(
    document_id: str,
    _usage: None = Depends(check_usage_limit),
    _increment: None = Depends(increment_usage),
    db: AgnosticDatabase = Depends(get_db),
) -> list[DocumentChangeSummary]:
    document = await DocumentRepository().find_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Document not found")

    changes = await DocumentChangeRepository().list_for_document(db, document_id)
    return [
        DocumentChangeSummary(
            id=change.id,
            created_at=change.created_at,
            changed_fields=change.changed_fields,
            job_id=change.job_id,
            content_hash=change.content_hash,
            previous_hash=change.previous_hash,
        )
        for change in changes
    ]


@router.get("/documents/{document_id}/changes/{change_id}/diff", response_model=dict[str, str])
async def diff_document_changes(
    document_id: str,
    change_id: str,
    _usage: None = Depends(check_usage_limit),
    _increment: None = Depends(increment_usage),
    db: AgnosticDatabase = Depends(get_db),
) -> dict[str, str]:
    document = await DocumentRepository().find_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Document not found")

    change = await db.document_changes.find_one({"id": change_id, "document_id": document_id})
    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    current_text = document.markdown or ""
    return {
        "change_id": change_id,
        "message": (
            "Full historical diffs are not stored. Compare current document text against "
            "recorded content hashes."
        ),
        "content_hash": change.get("content_hash") or "",
        "previous_hash": change.get("previous_hash") or "",
        "current_excerpt": current_text[:500],
    }


@router.get("/products/{slug}/overview-snapshots", response_model=list[OverviewSnapshot])
async def list_overview_snapshots(
    slug: str,
    _usage: None = Depends(check_usage_limit),
    _increment: None = Depends(increment_usage),
    db: AgnosticDatabase = Depends(get_db),
    service: ProductService = Depends(create_product_service),
) -> list[OverviewSnapshot]:
    product = await service.get_product_by_slug(db, slug)
    if not product:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Product not found")
    return await ProductIntelligenceRepository().list_overview_history(db, slug)
