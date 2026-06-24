from datetime import UTC, datetime

from motor.core import AgnosticDatabase
from pymongo import ReturnDocument

ANONYMOUS_LIMIT = 15


class ProductPreviewUsageService:
    COLLECTION = "product_preview_usage"

    @staticmethod
    def _current_month_key() -> str:
        return datetime.now(tz=UTC).strftime("%Y-%m")

    def _key_filter(self, *, token: str | None, ip: str) -> dict:
        if token:
            return {"token": token}
        return {"ip": ip, "token": {"$exists": False}}

    def _effective_count(self, doc: dict | None, month_key: str) -> int:
        if not doc:
            return 0
        if doc.get("month_key") != month_key:
            return 0
        return int(doc.get("count", 0))

    async def check_and_increment(
        self,
        db: AgnosticDatabase,
        *,
        token: str | None,
        ip: str,
        increment: bool = True,
    ) -> tuple[bool, int]:
        """Return (allowed, current_count).

        Keyed by preview token when present; falls back to IP when token is missing.
        Counts reset on the first day of each UTC calendar month.
        """
        key_filter = self._key_filter(token=token, ip=ip)
        month_key = self._current_month_key()
        collection = db[self.COLLECTION]

        if not increment:
            doc = await collection.find_one(key_filter, {"count": 1, "month_key": 1})
            current = self._effective_count(doc, month_key)
            return current < ANONYMOUS_LIMIT, current

        now = datetime.now(tz=UTC)
        set_on_insert: dict = {"first_seen": now, "count": 0, "month_key": month_key}
        if token:
            set_on_insert["token"] = token
        else:
            set_on_insert["ip"] = ip

        set_fields: dict = {"last_seen": now}
        if token:
            set_fields["ip"] = ip

        await collection.update_one(
            key_filter,
            {"$setOnInsert": set_on_insert, "$set": set_fields},
            upsert=True,
        )

        doc = await collection.find_one(key_filter, {"count": 1, "month_key": 1})
        current = self._effective_count(doc, month_key)

        if doc and doc.get("month_key") == month_key and current >= ANONYMOUS_LIMIT:
            return False, current

        if doc and doc.get("month_key") != month_key:
            updated = await collection.find_one_and_update(
                key_filter,
                {"$set": {"count": 1, "month_key": month_key, "last_seen": now}},
                return_document=ReturnDocument.AFTER,
            )
            return True, int(updated["count"]) if updated else 1

        updated = await collection.find_one_and_update(
            {**key_filter, "month_key": month_key, "count": {"$lt": ANONYMOUS_LIMIT}},
            {"$inc": {"count": 1}, "$set": {"last_seen": now}},
            return_document=ReturnDocument.AFTER,
        )
        if updated:
            return True, int(updated["count"])

        doc = await collection.find_one(key_filter, {"count": 1, "month_key": 1})
        current = self._effective_count(doc, month_key)
        return False, current
