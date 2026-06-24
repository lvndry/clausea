"""Migration framework.

Importing this package auto-discovers every ``NNN_*.py`` module in this
package, instantiates its :class:`~src.migrations.base.Migration` subclass, and
registers it with :data:`src.migrations.registry.registry`. The
:class:`src.services.migration_service.MigrationService` applies pending
entries on FastAPI startup.

To add a new migration: create ``NNN_description.py`` with a ``Migration``
subclass whose ``migration_id`` matches the filename stem. No other
registration needed.

Manual/interactive ops scripts (e.g. ``fix_product_names``, which prompts for
confirmation and targets a separate production URI) do NOT use the ``NNN_``
prefix and are therefore not auto-discovered — they must be run by hand.
"""

from __future__ import annotations

from src.migrations.base import Migration, MigrationResult
from src.migrations.registry import MigrationRegistry, autodiscover, registry

for _migration in autodiscover():
    registry.register(_migration)

__all__ = [
    "Migration",
    "MigrationResult",
    "MigrationRegistry",
    "autodiscover",
    "registry",
]
