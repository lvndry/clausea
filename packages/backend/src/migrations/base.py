"""Base class for versioned MongoDB data migrations.

Each migration is an idempotent, ordered transformation applied to the database
on FastAPI startup by :mod:`src.services.migration_service`. Migrations are
tracked in the ``_migrations`` collection so each runs exactly once per
environment. MongoDB is schemaless, so these are data migrations (renames,
backfills, config fixes) rather than DDL schema migrations — but the ordering
and exactly-once guarantees are just as important.

To add a new migration:
    1. Subclass :class:`Migration` with a unique, sortable ``migration_id``
       (format ``YYYYMMDD_NNNNNN_slug``) and a human-readable ``description``.
    2. Implement :meth:`upgrade` — it MUST be safe to re-run (idempotent).
    3. Register an instance in ``src/migrations/__init__.py``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase


@dataclass
class MigrationResult:
    """Outcome of a single migration attempt, recorded in ``_migrations``."""

    migration_id: str
    description: str
    status: str  # "applied" | "failed"
    applied_at: datetime
    duration_ms: int
    detail: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Migration(abc.ABC):
    """A single idempotent, ordered data migration applied to MongoDB.

    ``migration_id`` must be globally unique and sort lexicographically in the
    order migrations should be applied (e.g. ``20260214_000001_rename_companies``).
    """

    migration_id: str = ""
    description: str = ""

    @abc.abstractmethod
    async def upgrade(self, db: AgnosticDatabase) -> dict[str, Any]:
        """Apply the migration. Must be idempotent.

        Args:
            db: The database session to operate on.

        Returns:
            A detail dict (counts, changed slugs, etc.) stored alongside the
            migration record for auditability.
        """
        ...

    async def downgrade(self, db: AgnosticDatabase) -> None:
        """Optional rollback. Not invoked by the startup runner.

        Provided for manual ops recovery only.
        """
        raise NotImplementedError(f"{self.migration_id} has no downgrade")
