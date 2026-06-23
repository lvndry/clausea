"""Tests for policy change tracking: _diff_fields, DocumentChangeRepository, MonitoringScheduleRepository."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.document import Document
from src.pipeline import _diff_fields
from src.repositories.document_change_repository import DocumentChangeRepository
from src.repositories.monitoring_schedule_repository import MonitoringScheduleRepository


def _doc(**overrides) -> Document:
    defaults: dict = {
        "id": "doc1",
        "url": "https://example.com/privacy",
        "title": "Privacy Policy",
        "product_id": "prod1",
        "doc_type": "privacy_policy",
        "markdown": "# Privacy",
        "locale": "en-US",
        "regions": ["global"],
        "effective_date": None,
    }
    defaults.update(overrides)
    return Document(**defaults)


class TestDiffFields:
    def test_no_change(self) -> None:
        doc = _doc()
        assert _diff_fields(doc, doc) == []

    def test_markdown_changed(self) -> None:
        old = _doc(markdown="# Old policy content " * 20)
        new = _doc(markdown="# New policy content " * 20)
        assert "markdown" in _diff_fields(old, new)

    def test_title_changed(self) -> None:
        old = _doc(title="Old Title")
        new = _doc(title="New Title")
        assert "title" in _diff_fields(old, new)

    def test_doc_type_changed(self) -> None:
        old = _doc(doc_type="privacy_policy")
        new = _doc(doc_type="terms_of_service")
        assert "doc_type" in _diff_fields(old, new)

    def test_locale_changed(self) -> None:
        old = _doc(locale="en-US")
        new = _doc(locale="en-GB")
        assert "locale" in _diff_fields(old, new)

    def test_regions_changed(self) -> None:
        old = _doc(regions=["global"])
        new = _doc(regions=["US", "EU"])
        assert "regions" in _diff_fields(old, new)

    def test_effective_date_changed(self) -> None:
        old = _doc(effective_date=None)
        new = _doc(effective_date=datetime(2025, 1, 1))
        assert "effective_date" in _diff_fields(old, new)

    def test_multiple_fields_changed(self) -> None:
        old = _doc(title="Old", markdown="# old policy " * 20)
        new = _doc(title="New", markdown="# new policy " * 20)
        changed = _diff_fields(old, new)
        assert "title" in changed
        assert "markdown" in changed


class TestDocumentChangeRepository:
    @staticmethod
    def _changes_db() -> MagicMock:
        db = MagicMock()
        changes = MagicMock()
        changes.insert_one = AsyncMock()
        db.__getitem__ = MagicMock(return_value=changes)
        return db

    @pytest.mark.asyncio
    async def test_record_document_update(self) -> None:
        db = self._changes_db()
        db.products = MagicMock()
        db.products.find_one = AsyncMock(return_value={"slug": "acme"})

        existing = _doc(content_hash="hash123")
        await DocumentChangeRepository().record_document_update(
            db,
            existing_doc=existing,
            job_id="job123",
            changed_fields=["text"],
        )

        changes = db.__getitem__.return_value
        changes.insert_one.assert_called_once()
        inserted = changes.insert_one.call_args[0][0]
        assert inserted["document_id"] == existing.id
        assert inserted["job_id"] == "job123"
        assert inserted["changed_fields"] == ["text"]
        assert inserted["product_slug"] == "acme"
        assert inserted["content_hash"] == "hash123"

    @pytest.mark.asyncio
    async def test_record_document_update_without_job_id(self) -> None:
        db = self._changes_db()
        db.products = MagicMock()
        db.products.find_one = AsyncMock(return_value=None)

        existing = _doc(content_hash="hash456")
        await DocumentChangeRepository().record_document_update(
            db, existing_doc=existing, job_id=None, changed_fields=[]
        )

        changes = db.__getitem__.return_value
        inserted = changes.insert_one.call_args[0][0]
        assert inserted["job_id"] is None
        assert inserted["content_hash"] == "hash456"

    @pytest.mark.asyncio
    async def test_record_document_update_skips_without_content_hash(self) -> None:
        db = self._changes_db()
        db.products = MagicMock()
        db.products.find_one = AsyncMock(return_value=None)

        existing = _doc(content_hash=None)
        await DocumentChangeRepository().record_document_update(
            db, existing_doc=existing, job_id="job123", changed_fields=["markdown"]
        )

        db.__getitem__.return_value.insert_one.assert_not_called()


class TestMonitoringScheduleRepository:
    @pytest.mark.asyncio
    async def test_enroll_upserts(self) -> None:
        db = MagicMock()
        db.monitoring_schedules = MagicMock()
        db.monitoring_schedules.update_one = AsyncMock()

        repo = MonitoringScheduleRepository()
        await repo.enroll(db, product_slug="netflix", product_id="prod1")

        db.monitoring_schedules.update_one.assert_called_once()
        filter_arg, update_arg = db.monitoring_schedules.update_one.call_args[0]
        assert filter_arg == {"product_slug": "netflix"}
        assert "$setOnInsert" in update_arg

    @pytest.mark.asyncio
    async def test_find_due_returns_schedules(self) -> None:
        now = datetime.now()
        db = MagicMock()
        db.monitoring_schedules = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "id": "sched1",
                    "product_slug": "netflix",
                    "enrolled_at": now,
                    "next_crawl_due_at": now,
                    "interval_days": 30,
                    "enabled": True,
                }
            ]
        )
        db.monitoring_schedules.find = MagicMock(return_value=mock_cursor)

        repo = MonitoringScheduleRepository()
        results = await repo.find_due(db, limit=50)

        assert len(results) == 1
        assert results[0].product_slug == "netflix"
