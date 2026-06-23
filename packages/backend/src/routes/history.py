import difflib
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


class DiffResponse(BaseModel):
    version_a_id: str | None
    version_b_id: str
    unified_diff: str


@router.get("/documents/{document_id}/versions", response_model=list[DocumentChangeSummary])
async def list_document_versions(
    document_id: str,
    db: AgnosticDatabase = Depends(get_db),
) -> list[DocumentChangeSummary]:
    changes = await DocumentChangeRepository().list_for_document(db, document_id)
    if changes:
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

    # Legacy fallback for rows recorded before document_changes migration.
    cursor = (
        db.document_versions.find(
            {"document_id": document_id},
            {"text": 0, "markdown": 0, "raw_html": 0},
        )
        .sort("created_at", -1)
        .limit(50)
    )
    rows = await cursor.to_list(length=50)
    return [
        DocumentChangeSummary(
            id=str(row.get("id", "")),
            created_at=row.get("created_at"),
            changed_fields=row.get("changed_fields") or [],
            job_id=row.get("job_id"),
            content_hash=row.get("content_hash") or "",
            previous_hash=None,
        )
        for row in rows
    ]


@router.get("/documents/{document_id}/versions/{version_id}/diff", response_model=DiffResponse)
async def diff_document_versions(
    document_id: str,
    version_id: str,
    db: AgnosticDatabase = Depends(get_db),
) -> DiffResponse:
    target = await db.document_versions.find_one({"id": version_id, "document_id": document_id})
    if not target:
        raise HTTPException(status_code=404, detail="Version not found")

    previous = await db.document_versions.find_one(
        {"document_id": document_id, "created_at": {"$lt": target["created_at"]}},
        sort=[("created_at", -1)],
    )

    text_a = (previous or {}).get("markdown") or (previous or {}).get("text") or ""
    text_b = target.get("markdown") or target.get("text") or ""
    diff_lines = list(
        difflib.unified_diff(
            text_a.splitlines(keepends=True),
            text_b.splitlines(keepends=True),
            fromfile="previous",
            tofile="current",
            n=3,
        )
    )
    return DiffResponse(
        version_a_id=previous.get("id") if previous else None,
        version_b_id=version_id,
        unified_diff="".join(diff_lines)
        if diff_lines
        else "Diff unavailable for slim change records.",
    )


@router.get("/products/{slug}/overview-history", response_model=list[OverviewSnapshot])
async def list_overview_history(
    slug: str,
    db: AgnosticDatabase = Depends(get_db),
) -> list[OverviewSnapshot]:
    return await ProductOverviewHistoryRepository().find_by_product(db, slug)
