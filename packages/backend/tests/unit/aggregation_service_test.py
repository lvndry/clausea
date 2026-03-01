import json
from pathlib import Path
from typing import cast

from src.models.finding import Finding
from src.repositories.aggregation_repository import AggregationRepository
from src.repositories.document_repository import DocumentRepository
from src.repositories.finding_repository import FindingRepository
from src.services.aggregation_service import AggregationService


class _DummyRepo:
    async def find_by_product_id(self, *_args, **_kwargs):
        return []


def _service() -> AggregationService:
    return AggregationService(
        cast(DocumentRepository, _DummyRepo()),
        cast(FindingRepository, _DummyRepo()),
        cast(AggregationRepository, _DummyRepo()),
    )


def test_aggregate_findings_dedupes_by_category_and_value() -> None:
    service = _service()
    findings = [
        Finding(
            product_id="p1",
            document_id="d1",
            category="data_collection",
            value="Email address",
            normalized_value="email address",
        ),
        Finding(
            product_id="p1",
            document_id="d2",
            category="data_collection",
            value="Email address",
            normalized_value="email address",
        ),
    ]

    aggregated = service._aggregate_findings(findings)
    assert len(aggregated) == 1
    assert aggregated[0].category == "data_collection"
    assert sorted(aggregated[0].documents) == ["d1", "d2"]


def test_build_coverage_marks_missing_when_not_found() -> None:
    service = _service()
    findings = [
        Finding(
            product_id="p1",
            document_id="d1",
            category="user_rights",
            value="Access your data via settings",
        )
    ]

    coverage = service._build_coverage(findings, analyzed_docs=1)
    status_by_category = {item.category: item.status for item in coverage}
    assert status_by_category["user_rights"] == "found"
    assert status_by_category["data_collection"] == "missing"


def test_aggregation_fixture_shape() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures/aggregation_fixture.json"
    payload = json.loads(fixture_path.read_text())
    assert "coverage" in payload
    assert "findings" in payload
    assert isinstance(payload["findings"], list)
