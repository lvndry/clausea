"""Base repository class for data access operations.

Repositories handle all database access logic, providing a clean
interface for CRUD operations without owning database connections.
"""

from __future__ import annotations


class BaseRepository:
    """Base class for all repositories.

    Repositories are stateless and don't own database connections.
    Database instances are passed as parameters to methods.

    This design allows:
    - Easy testing (pass mock DB)
    - Thread safety (no shared state)
    - Clean separation of data access from business logic
    """

    pass
