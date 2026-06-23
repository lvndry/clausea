from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from motor.core import AgnosticDatabase
from pydantic import BaseModel

from src.core.database import get_db
from src.models.product_intelligence import OverviewSnapshot
from src.repositories.document_change_repository import DocumentChangeRepository
from src.repositories.product_overview_history_repository import ProductOverviewHistoryRepository

router = APIRouter(prefix="/history", tags=["history"])


class DocumentChangeSummary(BaseModel):
    id: str
    created_at: datetime
    changed_fields: list[str]
    job_id: str | None
    content_hash: str
    previous_hash: str | None


@router.get("/documents/{document_id}/versions", response_model=list[DocumentChangeSummary])
async def list_document_changes(
    document_id: str,
    db: AgnosticDatabase = Depends(get_db),
) -> list[DocumentChangeSummary]:
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


@router.get("/documents/{document_id}/versions/{change_id}/diff", response_model=dict[str, str])
async def diff_document_changes(
    document_id: str,
    change_id: str,
    db: AgnosticDatabase = Depends(get_db),
) -> dict[str, str]:
    change = await db.document_changes.find_one({"id": change_id, "document_id": document_id})
    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    current = await db.documents.find_one({"id": document_id}, {"markdown": 1})
    current_text = (current or {}).get("markdown") or ""
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


@router.get("/products/{slug}/overview-history", response_model=list[OverviewSnapshot])
async def list_overview_history(
    slug: str,
    db: AgnosticDatabase = Depends(get_db),
) -> list[OverviewSnapshot]:
    return await ProductOverviewHistoryRepository().find_by_product(db, slug)
