"""Migration framework.

Importing this package registers every auto-runnable migration with the
:data:`src.migrations.registry.registry`. The :class:`src.services.migration_service.MigrationService`
applies pending entries on FastAPI startup.

Manual/interactive ops scripts (e.g. ``fix_product_names``, which prompts for
confirmation and targets a separate production URI) are intentionally NOT
registered here — they must be run by hand.
"""

from __future__ import annotations

from src.migrations.backfill_orphan_citations import BackfillOrphanCitations
from src.migrations.base import Migration, MigrationResult
from src.migrations.fix_thin_evidence_products import FixThinEvidenceProducts
from src.migrations.migrate_companies_to_products import MigrateCompaniesToProducts
from src.migrations.registry import MigrationRegistry, registry

registry.register(MigrateCompaniesToProducts())
registry.register(FixThinEvidenceProducts())
registry.register(BackfillOrphanCitations())

__all__ = [
    "Migration",
    "MigrationResult",
    "MigrationRegistry",
    "registry",
]
