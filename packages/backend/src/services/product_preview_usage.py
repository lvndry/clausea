from datetime import UTC, datetime

from motor.core import AgnosticDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

ANONYMOUS_LIMIT = 5


class ProductPreviewUsageService:
    COLLECTION = "product_preview_usage"

    def _key_filter(self, *, token: str | None, ip: str) -> dict:
        if token:
            return {"token": token}
        return {"ip": ip, "token": {"$exists": False}}

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
        IP is stored as metadata only when token is the primary key.
        """
        key_filter = self._key_filter(token=token, ip=ip)

        if not increment:
            doc = await db[self.COLLECTION].find_one(key_filter, {"count": 1})
            current = doc["count"] if doc else 0
            return current < ANONYMOUS_LIMIT, current

        now = datetime.now(tz=UTC)
        update_filter = {**key_filter, "count": {"$lt": ANONYMOUS_LIMIT}}
        set_fields: dict = {"last_seen": now}
        set_on_insert: dict = {"first_seen": now}
        if token:
            set_fields["ip"] = ip
            set_on_insert["token"] = token
        else:
            set_on_insert["ip"] = ip

        try:
            doc = await db[self.COLLECTION].find_one_and_update(
                update_filter,
                {
                    "$inc": {"count": 1},
                    "$set": set_fields,
                    "$setOnInsert": set_on_insert,
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            doc = await db[self.COLLECTION].find_one_and_update(
                update_filter,
                {"$inc": {"count": 1}, "$set": set_fields},
                return_document=ReturnDocument.AFTER,
            )

        if doc is not None:
            return True, doc["count"]

        existing = await db[self.COLLECTION].find_one(key_filter, {"count": 1})
        current = existing["count"] if existing else ANONYMOUS_LIMIT
        return False, current
