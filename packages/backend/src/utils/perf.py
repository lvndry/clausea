import asyncio

import psutil

from src.core.logging import get_logger

logger = get_logger(__name__)


def get_memory_usage() -> dict[str, float]:
    """Get current memory usage statistics."""
    process = psutil.Process()
    memory_info = process.memory_info()

    # Get system memory
    system_memory = psutil.virtual_memory()

    return {
        "process_memory_mb": memory_info.rss / 1024 / 1024,  # Convert bytes to MB
        "process_memory_percent": process.memory_percent(),
        "system_memory_used_percent": system_memory.percent,
        "system_memory_available_gb": system_memory.available / 1024 / 1024 / 1024,
    }


def log_memory_usage(context: str = "") -> None:
    """Log current memory usage with context."""
    memory_stats = get_memory_usage()
    context_str = f" [{context}]" if context else ""

    logger.info(
        f"🧠 Memory Usage{context_str}: "
        f"Process: {memory_stats['process_memory_mb']:.1f}MB "
        f"({memory_stats['process_memory_percent']:.1f}%), "
        f"System: {memory_stats['system_memory_used_percent']:.1f}% used, "
        f"{memory_stats['system_memory_available_gb']:.1f}GB available"
    )


async def memory_monitor_task(interval: int = 30) -> None:
    """Background task to monitor memory usage periodically."""
    while True:
        log_memory_usage("Periodic Check")
        await asyncio.sleep(interval)
