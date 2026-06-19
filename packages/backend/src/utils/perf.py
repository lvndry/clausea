import asyncio
import resource
from pathlib import Path

import psutil

from src.core.logging import get_logger

logger = get_logger(__name__)


def _get_cgroup_memory_limit_bytes() -> int | None:
    """Read container memory limit from cgroup (v2 or v1)."""
    for path in [
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    ]:
        try:
            val = Path(path).read_text().strip()
            if val not in ("max", ""):
                return int(val)
        except Exception:
            pass
    return None


def _get_cgroup_memory_usage_bytes() -> int | None:
    """Read current container memory usage from cgroup."""
    for path in [
        "/sys/fs/cgroup/memory.current",
        "/sys/fs/cgroup/memory/memory.usage_in_bytes",
    ]:
        try:
            return int(Path(path).read_text().strip())
        except Exception:
            pass
    return None


def _get_proc_self_memory_bytes() -> int | None:
    """Read process RSS from /proc/self/status (portable; works in Railway containers)."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024  # kB → bytes
    except Exception:
        pass
    return None


def _get_rlimit_memory_bytes() -> int | None:
    """Return RLIMIT_AS soft limit as a proxy for the container memory ceiling."""
    try:
        soft, _ = resource.getrlimit(resource.RLIMIT_AS)
        if soft != resource.RLIM_INFINITY and soft > 0:
            return soft
    except Exception:
        pass
    return None


def get_memory_usage() -> dict[str, float]:
    """Get current memory usage statistics."""
    process = psutil.Process()
    memory_info = process.memory_info()

    cgroup_limit = _get_cgroup_memory_limit_bytes()
    cgroup_usage = _get_cgroup_memory_usage_bytes()

    if cgroup_limit is not None and cgroup_usage is not None:
        system_used_percent = (cgroup_usage / cgroup_limit) * 100
        system_available_gb = (cgroup_limit - cgroup_usage) / 1024 / 1024 / 1024
    else:
        # Fallback: per-process memory from /proc/self/status + RLIMIT_AS.
        # These are always correct inside Railway containers where /sys/fs/cgroup
        # is absent or read-only.
        proc_rss = _get_proc_self_memory_bytes()
        rlimit = _get_rlimit_memory_bytes()
        if proc_rss is not None and rlimit is not None:
            system_used_percent = (proc_rss / rlimit) * 100
            system_available_gb = (rlimit - proc_rss) / 1024 / 1024 / 1024
        else:
            system_memory = psutil.virtual_memory()
            system_used_percent = system_memory.percent
            system_available_gb = system_memory.available / 1024 / 1024 / 1024

    return {
        "process_memory_mb": memory_info.rss / 1024 / 1024,
        "process_memory_percent": process.memory_percent(),
        "system_memory_used_percent": system_used_percent,
        "system_memory_available_gb": system_available_gb,
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
