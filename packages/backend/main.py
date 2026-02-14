from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import config
from src.core.database import get_db
from src.core.db_indexes import ensure_all_indexes
from src.core.logging import setup_logging
from src.core.middleware import AuthMiddleware
from src.routes import (
    conversations,
    extension,
    list,
    paddle,
    products,
    promotion,
    q,
    subscription,
    users,
)

setup_logging()


async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle events."""
    # Startup: Ensure database indexes are created
    async with get_db() as db:
        await ensure_all_indexes(db)

    yield


app = FastAPI(title="Clausea API", lifespan=lifespan, version="1.0.0")  # type: ignore


app.add_middleware(
    CORSMiddleware,  # type: ignore
    allow_origins=config.cors.origins,
    allow_methods=config.cors.methods,
    allow_headers=config.cors.headers,
    allow_credentials=config.cors.credentials,
)
app.add_middleware(AuthMiddleware)  # type: ignore


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    """Health check endpoint to verify the API is running."""
    return {"status": "healthy", "message": "Clausea API is running"}


routes = [
    q.router,
    products.router,
    conversations.router,
    list.router,
    promotion.router,
    users.router,
    paddle.router,
    subscription.router,
    extension.router,
]

for route in routes:
    app.include_router(route)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
