from datetime import UTC, datetime

from motor.core import AgnosticDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

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

    async def _reset_month_if_needed(
        self,
        db: AgnosticDatabase,
        key_filter: dict,
        doc: dict | None,
        month_key: str,
        now: datetime,
    ) -> int:
        if doc is None:
            return 0
        if doc.get("month_key") == month_key:
            return int(doc.get("count", 0))

        await db[self.COLLECTION].update_one(
            key_filter,
            {"$set": {"count": 0, "month_key": month_key, "last_seen": now}},
        )
        return 0

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

        if not increment:
            doc = await db[self.COLLECTION].find_one(key_filter, {"count": 1, "month_key": 1})
            current = self._effective_count(doc, month_key)
            return current < ANONYMOUS_LIMIT, current

        now = datetime.now(tz=UTC)
        update_filter = {**key_filter, "count": {"$lt": ANONYMOUS_LIMIT}}
        set_fields: dict = {"last_seen": now, "month_key": month_key}
        set_on_insert: dict = {"first_seen": now, "month_key": month_key}
        if token:
            set_fields["ip"] = ip
            set_on_insert["token"] = token
        else:
            set_on_insert["ip"] = ip

        existing = await db[self.COLLECTION].find_one(key_filter)
        current = await self._reset_month_if_needed(db, key_filter, existing, month_key, now)

        if existing:
            if current >= ANONYMOUS_LIMIT:
                return False, current
            doc = await db[self.COLLECTION].find_one_and_update(
                update_filter,
                {"$inc": {"count": 1}, "$set": set_fields},
                return_document=ReturnDocument.AFTER,
            )
            if doc is not None:
                return True, int(doc["count"])
            existing = await db[self.COLLECTION].find_one(key_filter, {"count": 1, "month_key": 1})
            current = self._effective_count(existing, month_key)
            return False, current

        try:
            doc = await db[self.COLLECTION].find_one_and_update(
                key_filter,
                {
                    "$inc": {"count": 1},
                    "$set": set_fields,
                    "$setOnInsert": set_on_insert,
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            existing = await db[self.COLLECTION].find_one(key_filter, {"count": 1, "month_key": 1})
            current = self._effective_count(existing, month_key)
            return False, current

        if doc is not None:
            return True, int(doc["count"])
        return False, ANONYMOUS_LIMIT
