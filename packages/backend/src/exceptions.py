"""Custom exception classes for backend services."""


class NotFoundError(Exception):
    """Base class for not-found errors across services."""


class ProductNotFoundError(NotFoundError):
    """Raised when a product cannot be found by id or slug."""

    def __init__(self, *, product_id: str | None = None, slug: str | None = None):
        if product_id is not None:
            message = f"Product with id {product_id} not found"
        elif slug is not None:
            message = f"Product with slug {slug} not found"
        else:
            message = "Product not found"
        super().__init__(message)
