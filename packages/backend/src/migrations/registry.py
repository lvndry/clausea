"""Registry of all migrations known to the system.

Migrations are registered in :mod:`src.migrations.__init__` at import time and
ordered by ``migration_id`` so the runner applies them deterministically.
"""

from __future__ import annotations

from src.migrations.base import Migration


class MigrationRegistry:
    """Collects migrations and serves them in deterministic apply order."""

    def __init__(self) -> None:
        self._migrations: dict[str, Migration] = {}

    def register(self, migration: Migration) -> None:
        migration_id = migration.migration_id
        if not migration_id:
            raise ValueError("Migration is missing a migration_id")
        if migration_id in self._migrations:
            raise ValueError(f"Duplicate migration_id registered: {migration_id}")
        self._migrations[migration_id] = migration

    def all(self) -> list[Migration]:
        return sorted(self._migrations.values(), key=lambda m: m.migration_id)

    def pending(self, applied_ids: set[str]) -> list[Migration]:
        """Return registered migrations whose id is not in ``applied_ids``, in order."""
        return [m for m in self.all() if m.migration_id not in applied_ids]


registry = MigrationRegistry()
