"""Tests for policy change tracking: _diff_fields, DocumentVersionRepository, MonitoringScheduleRepository."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.document import Document
from src.pipeline import _diff_fields
from src.repositories.document_version_repository import DocumentVersionRepository
from src.repositories.monitoring_schedule_repository import MonitoringScheduleRepository


def _doc(**overrides) -> Document:
    defaults: dict = {
        "id": "doc1",
        "url": "https://example.com/privacy",
        "title": "Privacy Policy",
        "product_id": "prod1",
        "doc_type": "privacy_policy",
        "markdown": "# Privacy",
        "text": "This is the privacy policy text.",
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

    def test_text_changed(self) -> None:
        old = _doc(text="old text " * 50)
        new = _doc(text="new text " * 50)
        assert "text" in _diff_fields(old, new)

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
        old = _doc(title="Old", text="old " * 50)
        new = _doc(title="New", text="new " * 50)
        changed = _diff_fields(old, new)
        assert "title" in changed
        assert "text" in changed


class TestDocumentVersionRepository:
    @pytest.mark.asyncio
    async def test_archive_inserts_version(self) -> None:
        db = MagicMock()
        db.document_versions = MagicMock()
        db.document_versions.insert_one = AsyncMock()

        existing = _doc()
        repo = DocumentVersionRepository()
        await repo.archive(db, existing, job_id="job123", changed_fields=["text"])

        db.document_versions.insert_one.assert_called_once()
        inserted = db.document_versions.insert_one.call_args[0][0]
        assert inserted["document_id"] == existing.id
        assert inserted["job_id"] == "job123"
        assert inserted["changed_fields"] == ["text"]

    @pytest.mark.asyncio
    async def test_archive_with_no_job_id(self) -> None:
        db = MagicMock()
        db.document_versions = MagicMock()
        db.document_versions.insert_one = AsyncMock()

        existing = _doc()
        await DocumentVersionRepository().archive(db, existing, job_id=None, changed_fields=[])

        inserted = db.document_versions.insert_one.call_args[0][0]
        assert inserted["job_id"] is None


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
