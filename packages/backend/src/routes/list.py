from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/list")


@router.get("")
async def list_routes(request: Request) -> dict[str, Any]:
    """List all available routes in the application."""
    routes = []

    for route in request.app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            route_info = {
                "path": route.path,
                "methods": list(route.methods),
                "name": getattr(route, "name", None),
                "endpoint": (str(route.endpoint) if hasattr(route, "endpoint") else None),
            }
            routes.append(route_info)

    # Sort routes by path for better readability
    routes.sort(key=lambda x: x["path"])

    return {
        "total_routes": len(routes),
        "routes": routes,
        "base_url": str(request.base_url).rstrip("/"),
    }
