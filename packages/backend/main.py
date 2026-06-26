import asyncio
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from src.core.config import config
from src.core.database import close_motor_client, db_session
from src.core.db_indexes import ensure_active_job_unique_index, ensure_all_indexes
from src.core.logging import setup_logging
from src.core.middleware import AuthMiddleware
from src.repositories.pipeline_repository import PipelineRepository, StaleReapContext
from src.routes import (
    contact,
    extension,
    history,
    paddle,
    pipeline,
    products,
    promotion,
    subscription,
    users,
)
from src.services.migration_service import MigrationService

setup_logging()
logger = structlog.get_logger(service="main")

_startup_task: asyncio.Task[None] | None = None
_startup_complete = asyncio.Event()
_startup_failed = False


async def _initialize_database() -> None:
    """Run index creation and stale-job cleanup without blocking HTTP startup."""
    global _startup_failed
    try:
        if not config.database.mongodb_uri:
            logger.error("MONGO_URI is not set — database-backed routes will fail until configured")
            _startup_failed = True
            return

        async with db_session() as db:
            # Migrations first: they may create/rename collections that the
            # index step below then builds against.
            await MigrationService().run_pending(db)
            await ensure_all_indexes(db)
            # Reap orphaned jobs first (frees the active slot), THEN build the partial
            # unique index that enforces at-most-one active job per product.
            await PipelineRepository().mark_stale_as_failed(
                db, context=StaleReapContext.api_startup
            )
            await ensure_active_job_unique_index(db)
    except Exception:
        _startup_failed = True
        logger.exception("Database startup initialization failed")
    finally:
        _startup_complete.set()


async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle events."""
    global _startup_task, _startup_failed
    _startup_failed = False
    _startup_complete.clear()
    _startup_task = asyncio.create_task(_initialize_database())

    # Yield immediately so Railway liveness probes (/health) succeed while DB warms up.
    yield

    if _startup_task is not None:
        _startup_task.cancel()
        try:
            await _startup_task
        except asyncio.CancelledError:
            pass

    close_motor_client()


app = FastAPI(title="Clausea API", lifespan=lifespan, version="1.0.0")  # type: ignore

limiter = Limiter(key_func=get_remote_address, default_limits=[config.api.rate_limit_default])
app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
    ),
)
app.add_middleware(SlowAPIMiddleware)


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors.origins,
    allow_methods=config.cors.methods,
    allow_headers=config.cors.headers,
    allow_credentials=config.cors.credentials,
)
app.add_middleware(AuthMiddleware)  # type: ignore


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    """Liveness probe — returns 200 as soon as the process is serving HTTP."""
    return {"status": "healthy", "message": "Clausea API is running"}


@app.get("/health/ready")
async def readiness_check() -> JSONResponse:
    """Readiness probe — verifies MongoDB connectivity and startup initialization."""
    if not config.database.mongodb_uri:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "MONGO_URI is not configured"},
        )

    if not _startup_complete.is_set():
        return JSONResponse(
            status_code=503,
            content={"status": "starting", "reason": "Database initialization in progress"},
        )

    if _startup_failed:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "reason": "Database initialization failed"},
        )

    try:
        async with db_session() as db:
            await asyncio.wait_for(db.command("ping"), timeout=3.0)
    except Exception as exc:
        logger.warning("Readiness ping failed", error=str(exc))
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "MongoDB ping failed"},
        )

    return JSONResponse(content={"status": "ready", "message": "Clausea API is ready"})


routes = [
    products.router,
    users.router,
    paddle.router,
    subscription.router,
    extension.router,
    contact.router,
    pipeline.router,
    history.router,
]

if config.app.is_development:
    routes.append(promotion.router)

for route in routes:
    app.include_router(route)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
