"""Registry of all migrations known to the system.

Migrations live as ``NNN_description.py`` files inside this package. Each file
defines a :class:`~src.migrations.base.Migration` subclass.
:func:`autodiscover` imports every matching module, instantiates the subclass,
and registers it — so adding a migration is just dropping in a new file.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re

from src.migrations.base import Migration

_MIGRATION_FILE_RE = re.compile(r"^\d{3}_.+\.py$")


def autodiscover(package_name: str | None = __package__) -> list[Migration]:
    """Import every ``NNN_*.py`` module in *package_name* and collect Migration subclasses."""
    if package_name is None:
        return []
    package = importlib.import_module(package_name)
    discovered: list[Migration] = []

    for module_info in sorted(pkgutil.iter_modules(package.__path__), key=lambda m: m.name):
        if not _MIGRATION_FILE_RE.match(f"{module_info.name}.py"):
            continue
        module = importlib.import_module(f"{package_name}.{module_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Migration)
                and obj is not Migration
                and obj.__module__ == module.__name__
            ):
                discovered.append(obj())

    return discovered


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
