from datetime import UTC, datetime

from motor.core import AgnosticDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

ANONYMOUS_LIMIT = 3


class ExtensionUsageService:
    COLLECTION = "extension_anonymous_usage"

    async def check_and_increment(
        self, db: AgnosticDatabase, *, token: str, ip: str
    ) -> tuple[bool, int]:
        """Return (allowed, new_count). Keyed by extension install UUID, not IP.

        Uses atomic find_one_and_update with $lt filter to prevent race conditions.
        IP is stored as metadata for abuse detection only — it never gates access.
        """
        now = datetime.now(tz=UTC)
        try:
            doc = await db[self.COLLECTION].find_one_and_update(
                {"token": token, "count": {"$lt": ANONYMOUS_LIMIT}},
                {
                    "$inc": {"count": 1},
                    "$set": {"last_seen": now, "ip": ip},
                    "$setOnInsert": {"first_seen": now},
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # Two concurrent first-use requests raced; retry without upsert
            doc = await db[self.COLLECTION].find_one_and_update(
                {"token": token, "count": {"$lt": ANONYMOUS_LIMIT}},
                {"$inc": {"count": 1}, "$set": {"last_seen": now, "ip": ip}},
                return_document=ReturnDocument.AFTER,
            )
        if doc is not None:
            return True, doc["count"]
        # Filter didn't match — token exists at limit
        existing = await db[self.COLLECTION].find_one({"token": token}, {"count": 1})
        current = existing["count"] if existing else ANONYMOUS_LIMIT
        return False, current
