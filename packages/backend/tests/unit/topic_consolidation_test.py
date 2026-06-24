import pytest

from src.models.product_intelligence import RollupItem
from src.services.topic_consolidation import (
    consolidate_rollup_items,
    merge_clusters,
)


def _item(category: str, value: str, doc_id: str) -> RollupItem:
    return RollupItem(category=category, value=value, document_ids=[doc_id])


def test_merge_clusters_preserves_material_risk_attribute_when_many_members() -> None:
    members = [
        RollupItem(
            category="dangers",
            value=f"standard term {index}",
            document_ids=[f"d{index}"],
            attributes=[{"materiality": "standard_industry"}],
        )
        for index in range(60)
    ]
    members.append(
        RollupItem(
            category="dangers",
            value="they sell your data to brokers",
            document_ids=["d_risk"],
            attributes=[{"materiality": "material_risk"}],
        )
    )
    merged = merge_clusters(members, [list(range(len(members)))])[0]
    assert len(merged.attributes) <= 50
    assert any(attribute.get("materiality") == "material_risk" for attribute in merged.attributes)


def _bumble_content_ownership() -> list[RollupItem]:
    return [
        _item(
            "content_ownership", "Company may use uploaded content to create derivative works", "d0"
        ),
        _item(
            "content_ownership",
            "User grants Bumble a limited licence to host, process, review, moderate, "
            "generate, store and delete Pitch Content",
            "d1",
        ),
        _item(
            "content_ownership",
            "Users grant Bumble a limited license to host, process, review, moderate, "
            "generate, store and delete Pitch Content",
            "d2",
        ),
        _item(
            "content_ownership",
            "Company may use uploaded content to train AI models and create derivative works",
            "d3",
        ),
        _item(
            "content_ownership",
            "Uploading Pitch Content grants Bumble a limited license to host, process, "
            "review, moderate, generate, store and delete content for the BeePitched feature",
            "d4",
        ),
    ]


def test_merge_clusters_unions_documents_and_records_members() -> None:
    items = _bumble_content_ownership()
    merged = merge_clusters(items, [[0], [1, 2, 4], [3]])

    assert len(merged) == 3
    license_item = next(item for item in merged if len(item.document_ids) == 3)
    assert sorted(license_item.document_ids) == ["d1", "d2", "d4"]
    assert len(license_item.member_values) == 3


def test_merge_clusters_pivot_is_most_complete_value() -> None:
    items = _bumble_content_ownership()
    merged = merge_clusters(items, [[1, 2, 4]])
    assert "BeePitched feature" in merged[0].value


@pytest.mark.asyncio
async def test_consolidate_merges_paraphrases_keeps_distinct_clause_separate() -> None:
    items = _bumble_content_ownership()

    async def fake_judge(category, values):
        assert category == "content_ownership"
        return [[0], [1, 2, 4], [3]]

    result = await consolidate_rollup_items(items, judge=fake_judge)

    assert len(result) == 3
    values = [item.value for item in result]
    assert any("train AI models" in value for value in values)
    assert any("create derivative works" in value and "AI" not in value for value in values)


@pytest.mark.asyncio
async def test_consolidate_skips_single_finding_categories() -> None:
    items = [_item("content_ownership", "Only one finding here", "d0")]
    called = False

    async def fake_judge(category, values):
        nonlocal called
        called = True
        return [[0]]

    result = await consolidate_rollup_items(items, judge=fake_judge)
    assert result == items
    assert called is False


@pytest.mark.asyncio
async def test_consolidate_skips_non_narrative_categories() -> None:
    items = [
        _item("data_collection", "Email address", "d0"),
        _item("data_collection", "Phone number", "d1"),
    ]
    called = False

    async def fake_judge(category, values):
        nonlocal called
        called = True
        return [[0, 1]]

    result = await consolidate_rollup_items(items, judge=fake_judge)
    assert len(result) == 2
    assert called is False


@pytest.mark.asyncio
async def test_consolidate_degrades_to_unmerged_on_judge_failure() -> None:
    items = _bumble_content_ownership()

    async def failing_judge(category, values):
        raise RuntimeError("model unavailable")

    result = await consolidate_rollup_items(items, judge=failing_judge)
    assert len(result) == len(items)
