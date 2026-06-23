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

    def _count_after_increment(self, before: dict | None, month_key: str) -> int:
        if before is None:
            return 1
        if before.get("month_key") != month_key:
            return 1
        return self._effective_count(before, month_key) + 1

    def _build_increment_update(
        self,
        *,
        month_key: str,
        now: datetime,
        token: str | None,
        ip: str,
    ) -> tuple[list[dict], dict]:
        set_on_insert: dict = {"first_seen": now}
        extra_set: dict = {"month_key": month_key, "last_seen": now}
        if token:
            set_on_insert["token"] = token
            extra_set["ip"] = ip
        else:
            set_on_insert["ip"] = ip

        pipeline = [
            {
                "$set": {
                    **extra_set,
                    "count": {
                        "$cond": {
                            "if": {
                                "$lt": [
                                    {
                                        "$cond": {
                                            "if": {
                                                "$ne": [
                                                    {"$ifNull": ["$month_key", ""]},
                                                    month_key,
                                                ]
                                            },
                                            "then": 0,
                                            "else": {"$ifNull": ["$count", 0]},
                                        }
                                    },
                                    ANONYMOUS_LIMIT,
                                ]
                            },
                            "then": {
                                "$cond": {
                                    "if": {
                                        "$ne": [
                                            {"$ifNull": ["$month_key", ""]},
                                            month_key,
                                        ]
                                    },
                                    "then": 1,
                                    "else": {"$add": ["$count", 1]},
                                }
                            },
                            "else": {"$ifNull": ["$count", 0]},
                        }
                    },
                }
            }
        ]
        return pipeline, set_on_insert

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
        pipeline, set_on_insert = self._build_increment_update(
            month_key=month_key,
            now=now,
            token=token,
            ip=ip,
        )

        try:
            before = await db[self.COLLECTION].find_one_and_update(
                key_filter,
                pipeline,
                upsert=True,
                return_document=ReturnDocument.BEFORE,
                set_on_insert=set_on_insert,
            )
        except DuplicateKeyError:
            before = await db[self.COLLECTION].find_one_and_update(
                key_filter,
                pipeline,
                return_document=ReturnDocument.BEFORE,
            )

        if before is None:
            return True, 1

        before_count = self._effective_count(before, month_key)
        if before.get("month_key") == month_key and before_count >= ANONYMOUS_LIMIT:
            return False, before_count

        return True, self._count_after_increment(before, month_key)
