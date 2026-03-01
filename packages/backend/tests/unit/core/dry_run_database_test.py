from __future__ import annotations

import pytest

from src.core.dry_run_database import DryRunCollection, DryRunDatabase


class _FakeCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.called: dict[str, int] = {}

    def _bump(self, method: str) -> None:
        self.called[method] = self.called.get(method, 0) + 1

    async def insert_one(self, *_args, **_kwargs):
        self._bump("insert_one")
        raise AssertionError("insert_one should not be called in dry run")

    async def insert_many(self, *_args, **_kwargs):
        self._bump("insert_many")
        raise AssertionError("insert_many should not be called in dry run")

    async def update_one(self, *_args, **_kwargs):
        self._bump("update_one")
        raise AssertionError("update_one should not be called in dry run")

    async def delete_one(self, *_args, **_kwargs):
        self._bump("delete_one")
        raise AssertionError("delete_one should not be called in dry run")

    def find(self, *_args, **_kwargs):
        self._bump("find")
        return "cursor"


class _FakeDB:
    def __init__(self) -> None:
        self._collections = {"documents": _FakeCollection("documents")}

    def __getitem__(self, name: str):
        return self._collections[name]

    @property
    def documents(self):
        return self._collections["documents"]


@pytest.mark.asyncio
async def test_dry_run_collection_noops_writes_and_preserves_reads() -> None:
    fake = _FakeCollection("documents")
    coll = DryRunCollection(fake, enabled=True)

    assert coll.find({}) == "cursor"
    assert fake.called.get("find") == 1

    insert_result = await coll.insert_one({"id": "x"})
    assert isinstance(insert_result.inserted_id, str) and insert_result.inserted_id
    assert fake.called.get("insert_one") is None

    many_result = await coll.insert_many([{"id": "a"}, {"id": "b"}])
    assert len(many_result.inserted_ids) == 2
    assert fake.called.get("insert_many") is None

    update_result = await coll.update_one({"id": "x"}, {"$set": {"x": 1}})
    assert update_result.modified_count == 0
    assert fake.called.get("update_one") is None

    delete_result = await coll.delete_one({"id": "x"})
    assert delete_result.deleted_count == 0
    assert fake.called.get("delete_one") is None


@pytest.mark.asyncio
async def test_dry_run_database_wraps_collections_for_attr_and_item_access() -> None:
    fake_db = _FakeDB()
    db = DryRunDatabase(fake_db, enabled=True)

    coll_attr = db.documents
    coll_item = db["documents"]

    assert isinstance(coll_attr, DryRunCollection)
    assert isinstance(coll_item, DryRunCollection)

    await coll_attr.insert_one({"id": "x"})
    await coll_item.insert_one({"id": "y"})
