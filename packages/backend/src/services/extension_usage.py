from datetime import UTC, datetime

from motor.core import AgnosticDatabase

ANONYMOUS_LIMIT = 3


class ExtensionUsageService:
    COLLECTION = "extension_anonymous_usage"

    async def check_and_increment(
        self, db: AgnosticDatabase, *, token: str, ip: str
    ) -> tuple[bool, int]:
        """Return (allowed, new_count). Keyed by extension install UUID, not IP.

        IP is stored as metadata for abuse detection only — it never gates access.
        """
        doc = await db[self.COLLECTION].find_one({"token": token})
        current = doc["count"] if doc else 0

        if current >= ANONYMOUS_LIMIT:
            return False, current

        now = datetime.now(tz=UTC)
        await db[self.COLLECTION].update_one(
            {"token": token},
            {
                "$inc": {"count": 1},
                "$set": {"last_seen": now, "ip": ip},
                "$setOnInsert": {"first_seen": now},
            },
            upsert=True,
        )
        return True, current + 1
