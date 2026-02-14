from src.core.database import get_db
from src.dashboard.utils import run_async
from src.services.embedding_service import EmbeddingService


async def _embed_product_impl(product_slug: str) -> bool:
    async with get_db() as db:
        service = EmbeddingService()
        embedding_success = await service.embed_single_product(db, product_slug)
        return bool(embedding_success)


async def _embed_products_impl(
    product_slugs: list[str], max_concurrency: int = 3
) -> list[tuple[str, bool]]:
    async with get_db() as db:
        service = EmbeddingService()
        embedding_successes = await service.embed_multiple_products(
            db, product_slugs, max_concurrency=max_concurrency
        )
        return [(slug, bool(success)) for slug, success in embedding_successes]


def embed_product(product_slug: str) -> bool:
    """Embed a single product via the async service, executed safely from Streamlit.

    Returns True on success, False on failure.
    """
    result = run_async(_embed_product_impl(product_slug))
    return bool(result)


def embed_products(product_slugs: list[str], max_concurrency: int = 3) -> list[tuple[str, bool]]:
    """Embed multiple products via the async service, executed safely from Streamlit.

    Returns list of (slug, success) tuples. Returns empty list on failure.
    """
    result = run_async(_embed_products_impl(product_slugs, max_concurrency=max_concurrency))
    return result or []
