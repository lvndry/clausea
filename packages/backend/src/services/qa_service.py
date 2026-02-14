from __future__ import annotations

from src.rag import get_answer


async def ask(query: str, product_slug: str, namespace: str | None = None) -> str:
    answer = await get_answer(query, product_slug, namespace=namespace)
    return str(answer)
