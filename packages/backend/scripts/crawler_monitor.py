"""Production crawler + pipeline queue monitor with optional auto-fix.

Usage:
  uv run python scripts/crawler_monitor.py              # one snapshot
  uv run python scripts/crawler_monitor.py --logs     # include recent Railway log scan
  uv run python scripts/crawler_monitor.py --fix      # snapshot + remediate if needed
  uv run python scripts/crawler_monitor.py --loop     # 5-min loop with --logs --fix (24h watchdog)

Designed for production via railway run:
  railway run uv run python scripts/crawler_monitor.py --loop
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from src.core.config import DatabaseConfig
from src.core.database import db_session
from src.repositories.pipeline_repository import PipelineRepository

IN_PROGRESS = ("crawling", "synthesising", "generating_overview")
STATE_FILE = Path("/tmp/clausea_crawler_monitor_state.json")
STALL_GUARD_MINUTES = 20
STALL_RISK_MINUTES = 15
LOOP_INTERVAL_SECONDS = 300
WATCHDOG_HOURS = 24
REDEPLOY_COOLDOWN_MINUTES = 20
EXPECTED_FLEET_CONCURRENCY = int(os.getenv("CRAWLER_EXPECTED_CONCURRENCY", "8"))
REPLICA_COUNT = int(os.getenv("CRAWLER_REPLICA_COUNT", "2"))
WORKER_CONCURRENCY_SETTING = int(os.getenv("PIPELINE_WORKER_CONCURRENCY", "4"))
SAFE_CONCURRENCY_FALLBACK = 2
# Thresholds tuned for concurrency=4 experiment (worker.py OOM'd historically at ~13).
MEMORY_WARN_PROCESS_MB = 900
MEMORY_CRIT_PROCESS_MB = 1200
MEMORY_WARN_SYSTEM_PCT = 50
MEMORY_CRIT_SYSTEM_PCT = 70
MEMORY_WARN_DEFUNCT = 5
MEMORY_CRIT_DEFUNCT = 10
CONCURRENCY_DOWNGRADE_COOLDOWN_MINUTES = 60
MEMORY_USAGE_RE = re.compile(
    r"Memory Usage.*?Process: ([\d.]+)MB.*?System: ([\d.]+)% used, ([\d.]+)GB available"
)
WORKER_CONCURRENCY_RE = re.compile(r"concurrency=(\d+)", re.I)
OOM_RE = re.compile(
    r"(OOM|out of memory|killed process|SIGKILL|crashloop|MemoryError)",
    re.IGNORECASE,
)
FRESH_STEPS = [
    {
        "name": name,
        "status": "pending",
        "message": None,
        "progress_current": None,
        "progress_total": None,
        "progress_percent": None,
        "started_at": None,
        "completed_at": None,
        **({"has_explainer": None} if name == "generating_overview" else {}),
    }
    for name in ("crawling", "synthesising", "generating_overview")
]
RETRYABLE_FAILURE_CODES = frozenset(
    {
        "orphaned",
        "interrupted",
        "stalled",
        "Server restart — job was orphaned",
    }
)
LOG_UNUSUAL_PATTERNS = re.compile(
    r"(Pipeline job .* failed|Pipeline job .* stalled|DuplicateKey|defunct|"
    r"domain_circuit_breaker|orphaned|stalled|Error while closing Camoufox|"
    r"TypeError: Cannot read properties|Browser fetch failed|"
    r"Browser setup failed|Static content unusable and browser rendering failed|"
    r"Marked .* stale pipeline job|Boot sweep|Shutdown: marking)",
    re.IGNORECASE,
)
LOG_WATCH_PATTERNS = re.compile(
    r"(?i)(Pipeline worker started|Claimed job|Boot sweep|Shutdown: marking|"
    r"stalled \(no progress|orphaned|interrupted|Pipeline worker stopped|"
    r"grace exceeded|Marked .* stale pipeline job|domain_circuit_breaker)",
)
LOG_SKIP_PATTERNS = re.compile(
    r"(Process memory snapshot|Memory Usage \[Periodic|storage complete:)",
    re.IGNORECASE,
)


def _count_defunct_camoufox(log_text: str) -> int:
    blocks = re.findall(r"Found 'camoufox' processes:\\n([^\"\\]+)", log_text)
    if not blocks:
        return 0
    return len(re.findall(r"<defunct>", blocks[-1]))


def _parse_memory_signals(log_text: str) -> dict[str, Any]:
    process_mbs = [float(m.group(1)) for m in MEMORY_USAGE_RE.finditer(log_text)]
    system_pcts = [float(m.group(2)) for m in MEMORY_USAGE_RE.finditer(log_text)]
    avail_gbs = [float(m.group(3)) for m in MEMORY_USAGE_RE.finditer(log_text)]
    concurrencies = [int(m.group(1)) for m in WORKER_CONCURRENCY_RE.finditer(log_text)]

    return {
        "process_mb_max": max(process_mbs) if process_mbs else None,
        "process_mb_latest": process_mbs[-1] if process_mbs else None,
        "system_pct_max": max(system_pcts) if system_pcts else None,
        "system_pct_latest": system_pcts[-1] if system_pcts else None,
        "avail_gb_latest": avail_gbs[-1] if avail_gbs else None,
        "worker_concurrency": concurrencies[-1] if concurrencies else WORKER_CONCURRENCY_SETTING,
        "defunct_camoufox": _count_defunct_camoufox(log_text),
        "oom_detected": bool(OOM_RE.search(log_text)),
        "samples": len(process_mbs),
    }


def _memory_alerts(memory: dict[str, Any]) -> list[str]:
    alerts: list[str] = []
    proc_max = memory.get("process_mb_max")
    sys_max = memory.get("system_pct_max")
    defunct = int(memory.get("defunct_camoufox") or 0)
    concurrency = int(memory.get("worker_concurrency") or WORKER_CONCURRENCY_SETTING)

    if memory.get("oom_detected"):
        alerts.append("OOM/crash signal in recent crawler logs")
    if proc_max is not None and proc_max >= MEMORY_CRIT_PROCESS_MB:
        alerts.append(
            f"memory critical: worker process peaked at {proc_max:.0f}MB "
            f"(limit warn={MEMORY_WARN_PROCESS_MB} crit={MEMORY_CRIT_PROCESS_MB})"
        )
    elif proc_max is not None and proc_max >= MEMORY_WARN_PROCESS_MB:
        alerts.append(
            f"memory elevated: worker process peaked at {proc_max:.0f}MB "
            f"(concurrency={concurrency})"
        )
    if sys_max is not None and sys_max >= MEMORY_CRIT_SYSTEM_PCT:
        alerts.append(f"memory critical: container at {sys_max:.0f}% system memory")
    elif sys_max is not None and sys_max >= MEMORY_WARN_SYSTEM_PCT:
        alerts.append(f"memory elevated: container at {sys_max:.0f}% system memory")
    if defunct >= MEMORY_CRIT_DEFUNCT:
        alerts.append(f"memory risk: {defunct} defunct camoufox processes (browser leak)")
    elif defunct >= MEMORY_WARN_DEFUNCT:
        alerts.append(f"memory watch: {defunct} defunct camoufox processes")
    return alerts


def _memory_pressure_critical(alerts: list[str]) -> bool:
    return any(
        phrase in alert for alert in alerts for phrase in ("memory critical", "OOM/crash signal")
    )


def _downgrade_concurrency(meta: dict[str, Any]) -> str | None:
    """Drop PIPELINE_WORKER_CONCURRENCY to SAFE_CONCURRENCY_FALLBACK if under pressure."""
    now = _utc_now()
    last = meta.get("concurrency_downgraded_at")
    if last:
        try:
            if (now - datetime.fromisoformat(str(last))).total_seconds() < (
                CONCURRENCY_DOWNGRADE_COOLDOWN_MINUTES * 60
            ):
                return None
        except ValueError:
            pass
    try:
        proc = subprocess.run(
            [
                "railway",
                "variable",
                "set",
                "--service",
                "crawler",
                f"PIPELINE_WORKER_CONCURRENCY={SAFE_CONCURRENCY_FALLBACK}",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            return f"concurrency downgrade failed: {(proc.stdout + proc.stderr).strip()[:120]}"
        meta["concurrency_downgraded_at"] = now.isoformat()
        meta["concurrency_was"] = WORKER_CONCURRENCY_SETTING
        return f"downgraded PIPELINE_WORKER_CONCURRENCY to {SAFE_CONCURRENCY_FALLBACK} (OOM guard)"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"concurrency downgrade failed: {exc}"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _heartbeat_age_minutes(job: dict[str, Any], now: datetime) -> float | None:
    hb = job.get("last_heartbeat") or job.get("updated_at")
    if hb is None:
        return None
    if isinstance(hb, datetime) and hb.tzinfo is not None:
        hb = hb.replace(tzinfo=None)
    return (now - hb).total_seconds() / 60.0


def _stall_risk_jobs(jobs: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    at_risk: list[tuple[float, dict[str, Any]]] = []
    for job in jobs:
        if job.get("status") not in IN_PROGRESS:
            continue
        age = _heartbeat_age_minutes(job, now)
        if age is not None and age >= STALL_RISK_MINUTES:
            at_risk.append((age, job))
    at_risk.sort(key=lambda pair: -pair[0])
    return [job for _, job in at_risk]


def _fmt_ts(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def _step_summary(steps: list[dict[str, Any]] | None) -> str:
    if not steps:
        return "-"
    running = next((s for s in steps if s.get("status") == "running"), None)
    if running:
        name = running.get("name", "?")
        msg = running.get("message") or ""
        cur = running.get("progress_current")
        total = running.get("progress_total")
        pct = running.get("progress_percent")
        if cur is not None and total is not None:
            progress = f"{cur}/{total}"
            if pct is not None:
                progress += f" ({pct:.0f}%)"
            return f"{name}: {msg or progress}".strip(": ")
        return f"{name}: {msg}".strip(": ") if msg else name
    for name in ("generating_overview", "synthesising", "crawling"):
        step = next((s for s in steps if s.get("name") == name), None)
        if step and step.get("status") == "completed":
            return f"{name} done"
    return "-"


async def _mongo_snapshot() -> dict[str, Any]:
    cfg = DatabaseConfig()
    if not cfg.mongodb_uri:
        raise SystemExit("No MONGO_URI configured")

    client = AsyncIOMotorClient(cfg.mongodb_uri)
    db = client[cfg.mongodb_database]
    now = _utc_now()

    products = await db.products.count_documents({})
    by_status = {
        row["_id"]: row["n"]
        async for row in db.pipeline_jobs.aggregate(
            [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
        )
    }
    total_jobs = sum(by_status.values())
    active = await db.pipeline_jobs.count_documents({"active": True})
    pending = by_status.get("pending", 0)
    running = sum(by_status.get(s, 0) for s in IN_PROGRESS)
    quarantined = await db.pipeline_jobs.count_documents(
        {"status": "failed", "auto_retry_disabled": True}
    )
    recent_failed = await db.pipeline_jobs.count_documents(
        {"status": "failed", "updated_at": {"$gte": now - timedelta(minutes=15)}}
    )
    recent_completed = await db.pipeline_jobs.count_documents(
        {"status": "completed", "completed_at": {"$gte": now - timedelta(minutes=15)}}
    )

    stale_cutoff = now - timedelta(minutes=25)
    stale = (
        await db.pipeline_jobs.find(
            {
                "status": {"$in": list(IN_PROGRESS)},
                "$or": [
                    {"last_heartbeat": {"$lt": stale_cutoff}},
                    {"last_heartbeat": None, "updated_at": {"$lt": stale_cutoff}},
                ],
            },
            {
                "_id": 0,
                "product_slug": 1,
                "status": 1,
                "attempts": 1,
                "last_heartbeat": 1,
                "updated_at": 1,
            },
        )
        .sort("updated_at", 1)
        .limit(20)
        .to_list(length=20)
    )

    dupes = await db.pipeline_jobs.aggregate(
        [
            {"$match": {"active": True}},
            {"$group": {"_id": "$product_slug", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
            {"$sort": {"n": -1}},
        ]
    ).to_list(length=20)

    in_progress = (
        await db.pipeline_jobs.find(
            {"status": {"$in": list(IN_PROGRESS)}},
            {
                "_id": 0,
                "product_slug": 1,
                "product_name": 1,
                "status": 1,
                "attempts": 1,
                "documents_found": 1,
                "documents_stored": 1,
                "analyses_skipped": 1,
                "force_reanalyze": 1,
                "last_heartbeat": 1,
                "updated_at": 1,
                "steps": 1,
            },
        )
        .sort("updated_at", -1)
        .to_list(length=50)
    )

    recent_terminal = (
        await db.pipeline_jobs.find(
            {
                "status": {"$in": ["completed", "failed", "no_documents", "interrupted"]},
                "updated_at": {"$gte": now - timedelta(minutes=15)},
            },
            {
                "_id": 0,
                "product_slug": 1,
                "status": 1,
                "error": 1,
                "error_detail": 1,
                "documents_found": 1,
                "documents_stored": 1,
                "analyses_skipped": 1,
                "completed_at": 1,
                "updated_at": 1,
            },
        )
        .sort("updated_at", -1)
        .limit(10)
        .to_list(length=10)
    )

    watch_jobs = (
        await db.pipeline_jobs.find(
            {"status": {"$in": list(IN_PROGRESS)}},
            {
                "_id": 0,
                "product_slug": 1,
                "product_name": 1,
                "status": 1,
                "attempts": 1,
                "documents_found": 1,
                "documents_stored": 1,
                "last_heartbeat": 1,
                "updated_at": 1,
                "steps": 1,
                "error": 1,
                "error_detail": 1,
            },
        )
        .sort("updated_at", -1)
        .limit(8)
        .to_list(length=8)
    )

    completed_total = by_status.get("completed", 0)
    failed_total = by_status.get("failed", 0)
    interrupted_total = by_status.get("interrupted", 0)
    blocked = await db.pipeline_jobs.count_documents(
        {"active": False, "status": {"$nin": ["completed", "failed", "no_documents"]}}
    )

    stall_risk = _stall_risk_jobs(in_progress, now)

    client.close()

    alerts: list[str] = []
    if dupes:
        alerts.append("duplicate active jobs: " + ", ".join(f"{d['_id']}={d['n']}" for d in dupes))
    if stale:
        alerts.append(
            "stale in-progress: "
            + ", ".join(
                f"{j.get('product_slug')}({j.get('status')},att={j.get('attempts', 0)})"
                for j in stale
            )
        )
    if quarantined:
        alerts.append(f"quarantined failed jobs: {quarantined}")
    if recent_failed >= 20:
        alerts.append(f"high recent failure volume: {recent_failed} in 15m")
    if active == 0 or (pending == 0 and running == 0 and active > 0):
        alerts.append(f"inconsistent queue: active={active} pending={pending} running={running}")
    if blocked:
        alerts.append(f"blocked jobs (active=false, non-terminal): {blocked}")
    if interrupted_total:
        alerts.append(f"interrupted jobs awaiting boot requeue: {interrupted_total}")
    if pending >= 20 and running == 0:
        alerts.append(f"workers idle: {pending} pending but 0 in progress")
    elif pending >= 20 and running < max(2, EXPECTED_FLEET_CONCURRENCY // 2):
        alerts.append(
            f"low utilization: {running}/{EXPECTED_FLEET_CONCURRENCY} slots with {pending} pending"
        )
    if completed_total == 0 and pending >= 100 and running <= 2:
        alerts.append("zero completions with large backlog — possible worker wedge")

    if stall_risk:
        alerts.append(
            "stall risk (hb > "
            f"{STALL_RISK_MINUTES}m, kills at {STALL_GUARD_MINUTES}m): "
            + ", ".join(
                f"{j.get('product_slug')}({j.get('status')},{_heartbeat_age_minutes(j, now):.0f}m)"
                for j in stall_risk
            )
        )

    return {
        "products": products,
        "total_jobs": total_jobs,
        "by_status": by_status,
        "active": active,
        "pending": pending,
        "running": running,
        "completed_total": completed_total,
        "failed_total": failed_total,
        "interrupted_total": interrupted_total,
        "blocked": blocked,
        "quarantined": quarantined,
        "recent_failed": recent_failed,
        "recent_completed": recent_completed,
        "in_progress": in_progress,
        "recent_terminal": recent_terminal,
        "watch_jobs": watch_jobs,
        "stall_risk": stall_risk,
        "alerts": alerts,
    }


def _railway_crawler_line() -> tuple[str | None, list[str]]:
    alerts: list[str] = []
    try:
        proc = subprocess.run(
            ["railway", "status"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        text = proc.stdout + proc.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, [f"railway status failed: {exc}"]

    match = re.search(r"crawler:.*", text)
    if match:
        line = match.group(0).strip()
        if "Online" not in line or "running" not in line:
            alerts.append(f"crawler not healthy: {line}")
        return line, alerts
    alerts.append("crawler line not found in railway status")
    return None, alerts


def _extract_log_event(line: str) -> str:
    if "event=" in line:
        m = re.search(r'event="([^"]+)"', line)
        if m:
            return m.group(1)[:240]
    return line[:240]


def _railway_logs_tail(limit: int = 150) -> str:
    try:
        proc = subprocess.run(
            ["railway", "logs", "--service", "crawler", "--tail", str(limit)],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        return proc.stdout + proc.stderr
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _railway_log_unusual(limit: int = 150) -> list[str]:
    text = _railway_logs_tail(limit)
    if not text.strip():
        return ["(could not fetch railway logs)"]

    hits: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("---"):
            continue
        if LOG_UNUSUAL_PATTERNS.search(line) and not LOG_SKIP_PATTERNS.search(line):
            hits.append(_extract_log_event(line))
    return hits[-10:] if hits else []


def _railway_log_watch(limit: int = 200) -> list[str]:
    text = _railway_logs_tail(limit)
    if not text.strip():
        return ["(could not fetch railway logs)"]

    hits: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("---"):
            continue
        if LOG_WATCH_PATTERNS.search(line) and not LOG_SKIP_PATTERNS.search(line):
            hits.append(_extract_log_event(line))
    return hits[-12:] if hits else []


def _job_metrics(job: dict[str, Any]) -> dict[str, int | str]:
    return {
        "slug": str(job.get("product_slug", "?")),
        "status": str(job.get("status", "?")),
        "found": int(job.get("documents_found") or 0),
        "stored": int(job.get("documents_stored") or 0),
        "skipped": int(job.get("analyses_skipped") or 0),
    }


def _load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"jobs": {}, "meta": {}}
    try:
        raw = json.loads(STATE_FILE.read_text())
        if isinstance(raw, dict):
            if "jobs" in raw or "meta" in raw:
                return {
                    "jobs": raw.get("jobs") if isinstance(raw.get("jobs"), dict) else {},
                    "meta": raw.get("meta") if isinstance(raw.get("meta"), dict) else {},
                }
            return {"jobs": raw, "meta": {}}
    except (OSError, json.JSONDecodeError):
        pass
    return {"jobs": {}, "meta": {}}


def _save_state(jobs: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    payload = {
        "jobs": {str(j["slug"]): j for j in (_job_metrics(job) for job in jobs)},
        "meta": meta,
    }
    try:
        STATE_FILE.write_text(json.dumps(payload, indent=2))
    except OSError:
        pass


def _eta_hours(completed: int, total: int, recent_completed_15m: int) -> str | None:
    remaining = max(total - completed, 0)
    if remaining == 0:
        return "done"
    if recent_completed_15m <= 0:
        return None
    rate_per_hour = recent_completed_15m * 4
    hours = remaining / rate_per_hour
    return f"~{hours:.1f}h at {rate_per_hour:.0f}/h (from last 15m)"


async def _auto_fix(data: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    """Remediate common pipeline issues. Returns actions taken."""
    actions: list[str] = []
    now = _utc_now()
    repo = PipelineRepository()

    async with db_session() as db:
        interrupted = await repo.requeue_interrupted_jobs(db)
        if interrupted:
            actions.append(f"requeued {interrupted} interrupted job(s)")

        blocked = data.get("blocked", 0)
        if blocked:
            result = await db.pipeline_jobs.update_many(
                {"status": "interrupted", "active": False},
                {
                    "$set": {
                        "status": "pending",
                        "active": True,
                        "error": None,
                        "error_detail": None,
                        "updated_at": now,
                    }
                },
            )
            if result.modified_count:
                actions.append(f"unblocked {result.modified_count} interrupted job(s)")

        quarantined = await db.pipeline_jobs.find(
            {
                "status": "failed",
                "auto_retry_disabled": True,
                "$or": [
                    {"error": {"$in": list(RETRYABLE_FAILURE_CODES)}},
                    {"auto_retry_disabled_reason": {"$regex": "attempt limit", "$options": "i"}},
                ],
            },
            {"id": 1, "product_slug": 1},
        ).to_list(length=50)
        if quarantined:
            slugs = [j["product_slug"] for j in quarantined]
            result = await db.pipeline_jobs.update_many(
                {"product_slug": {"$in": slugs}, "status": "failed"},
                {
                    "$set": {
                        "status": "pending",
                        "active": True,
                        "steps": FRESH_STEPS,
                        "error": None,
                        "error_detail": None,
                        "attempts": 0,
                        "auto_retry_disabled": False,
                        "auto_retry_disabled_reason": None,
                        "force_reanalyze": True,
                        "updated_at": now,
                    }
                },
            )
            if result.modified_count:
                actions.append(f"reset {result.modified_count} quarantined failed job(s)")

        requeued_failed = await repo.requeue_failed_jobs(db)
        if requeued_failed:
            actions.append(f"requeued {requeued_failed} failed job(s)")

    pending = data.get("pending", 0)
    running = data.get("running", 0)
    alerts = data.get("alerts") or []
    needs_redeploy = any(
        phrase in alert
        for alert in alerts
        for phrase in (
            "workers idle",
            "low utilization",
            "zero completions",
            "stale in-progress",
        )
    )
    if pending >= 20 and running == 0:
        needs_redeploy = True

    last_redeploy = meta.get("last_redeploy_at")
    redeploy_cooldown_ok = True
    if last_redeploy:
        try:
            last_dt = datetime.fromisoformat(str(last_redeploy))
            redeploy_cooldown_ok = (now - last_dt).total_seconds() >= REDEPLOY_COOLDOWN_MINUTES * 60
        except ValueError:
            pass

    if needs_redeploy and redeploy_cooldown_ok:
        try:
            proc = subprocess.run(
                ["railway", "redeploy", "--service", "crawler", "--yes"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode == 0:
                meta["last_redeploy_at"] = now.isoformat()
                actions.append("triggered crawler redeploy (cooldown reset)")
            else:
                err = (proc.stdout + proc.stderr).strip()[:200]
                actions.append(f"redeploy skipped/failed: {err or proc.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            actions.append(f"redeploy failed: {exc}")

    if actions:
        meta["last_fix_at"] = now.isoformat()
    return actions


def _auto_fix_memory(data: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    memory = data.get("memory") or {}
    if not memory.get("samples"):
        return actions
    mem_alerts = _memory_alerts(memory)
    concurrency = int(memory.get("worker_concurrency") or WORKER_CONCURRENCY_SETTING)
    if _memory_pressure_critical(mem_alerts) and concurrency > SAFE_CONCURRENCY_FALLBACK:
        action = _downgrade_concurrency(meta)
        if action:
            actions.append(action)
    return actions


def _progress_deltas(
    current_jobs: list[dict[str, Any]], previous: dict[str, dict[str, int | str]]
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    seen: set[str] = set()
    for job in current_jobs:
        cur = _job_metrics(job)
        slug = str(cur["slug"])
        seen.add(slug)
        prev = previous.get(slug)
        if prev is None:
            if cur["status"] != "pending" or cur["found"] or cur["stored"]:
                deltas.append(
                    {
                        **cur,
                        "delta_found": cur["found"],
                        "delta_stored": cur["stored"],
                        "delta_skipped": cur["skipped"],
                        "kind": "started",
                    }
                )
            continue
        df = cur["found"] - int(prev.get("found") or 0)
        ds = cur["stored"] - int(prev.get("stored") or 0)
        dsk = cur["skipped"] - int(prev.get("skipped") or 0)
        if prev.get("status") != cur["status"] or df or ds or dsk:
            deltas.append(
                {
                    **cur,
                    "delta_found": df,
                    "delta_stored": ds,
                    "delta_skipped": dsk,
                    "kind": "update",
                }
            )
    for slug, prev in previous.items():
        if slug not in seen and prev.get("status") in IN_PROGRESS:
            deltas.append(
                {
                    "slug": slug,
                    "status": "finished",
                    "found": int(prev.get("found") or 0),
                    "stored": int(prev.get("stored") or 0),
                    "skipped": int(prev.get("skipped") or 0),
                    "delta_found": 0,
                    "delta_stored": 0,
                    "delta_skipped": 0,
                    "kind": "finished",
                }
            )
    return deltas


def _format_delta(n: int, label: str) -> str:
    if n > 0:
        return f"+{n} {label}"
    if n < 0:
        return f"{n} {label}"
    return ""


def _format_job_error(job: dict[str, Any]) -> str:
    detail = job.get("error_detail")
    code = job.get("error")
    if detail:
        return str(detail)
    if code:
        return str(code)
    return ""


def _print_snapshot(
    data: dict[str, Any],
    railway_line: str | None,
    log_hits: list[str] | None,
    *,
    log_watch: list[str] | None = None,
    progress_deltas: list[dict[str, Any]],
    now: datetime,
    fix_actions: list[str] | None = None,
) -> None:
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_status = data["by_status"]
    print(f"=== crawler-monitor {ts} ===")

    print("[RAILWAY]")
    print(f"  {railway_line or 'unknown'}")

    print("[QUEUE]")
    status_bits = " ".join(f"{k}={v}" for k, v in sorted(by_status.items()))
    print(
        f"  products={data['products']} total_jobs={data['total_jobs']} active={data['active']} "
        f"pending={data['pending']} in_progress={data['running']}"
    )
    print(f"  {status_bits}")
    print(
        f"  quarantined_failed={data['quarantined']} blocked={data.get('blocked', 0)} "
        f"recent_failed_15m={data['recent_failed']} recent_completed_15m={data['recent_completed']}"
    )

    completed = data.get("completed_total", 0)
    total = data.get("total_jobs", 0)
    eta = _eta_hours(completed, total, data.get("recent_completed", 0))
    print(
        f"[BATCH] completed={completed}/{total} failed={data.get('failed_total', 0)} "
        f"utilization={data['running']}/{EXPECTED_FLEET_CONCURRENCY}"
    )
    if eta:
        print(f"  eta: {eta}")
    elif completed < total:
        print("  eta: (waiting for first completions to estimate)")

    memory = data.get("memory") or {}
    concurrency = memory.get("worker_concurrency") or WORKER_CONCURRENCY_SETTING
    fleet_cap = int(concurrency) * REPLICA_COUNT
    print(
        f"[MEMORY] concurrency={concurrency}/replica fleet_cap={fleet_cap} "
        f"(experiment: was 2, now {WORKER_CONCURRENCY_SETTING})"
    )
    if memory.get("samples"):
        print(
            f"  worker_process: latest={memory.get('process_mb_latest')}MB "
            f"peak={memory.get('process_mb_max')}MB | "
            f"container: latest={memory.get('system_pct_latest')}% "
            f"peak={memory.get('system_pct_max')}% | "
            f"avail={memory.get('avail_gb_latest')}GB"
        )
        print(
            f"  defunct_camoufox={memory.get('defunct_camoufox', 0)} "
            f"(warn>={MEMORY_WARN_DEFUNCT} crit>={MEMORY_CRIT_DEFUNCT}) | "
            f"oom_in_logs={'yes' if memory.get('oom_detected') else 'no'}"
        )
        print(
            f"  thresholds: process warn={MEMORY_WARN_PROCESS_MB}MB "
            f"crit={MEMORY_CRIT_PROCESS_MB}MB | system warn={MEMORY_WARN_SYSTEM_PCT}% "
            f"crit={MEMORY_CRIT_SYSTEM_PCT}%"
        )
    else:
        print("  (no periodic memory samples in recent logs — use --logs)")

    working = [j for j in data["in_progress"] if j.get("status") != "pending"]
    working_sorted = sorted(
        working,
        key=lambda j: (-(j.get("documents_found") or 0), j.get("product_slug", "")),
    )
    print(f"[DOCS_PROGRESS] working={len(working_sorted)} pending={data['pending']}")
    for job in working_sorted:
        slug = job.get("product_slug", "?")
        status = job.get("status", "?")
        found = job.get("documents_found", 0)
        stored = job.get("documents_stored", 0)
        skipped = job.get("analyses_skipped", 0)
        step = _step_summary(job.get("steps"))
        print(
            f"  {slug:20} {status:18} found={found:4} stored={stored:4} analysis_done={skipped:3} | {step}"
        )
    if not working_sorted:
        print("  (no crawls/analysis running yet)")

    watch_jobs = data.get("watch_jobs") or []
    if watch_jobs:
        print(f"[TOP_ACTIVE] latest={len(watch_jobs)}")
        for job in watch_jobs:
            slug = job.get("product_slug", "?")
            status = job.get("status", "?")
            att = job.get("attempts", 0)
            found = job.get("documents_found", 0)
            stored = job.get("documents_stored", 0)
            step = _step_summary(job.get("steps"))
            age = _heartbeat_age_minutes(job, now)
            age_s = f"{age:.0f}m since hb" if age is not None else "no hb yet"
            print(
                f"  {slug} | {status} att={att} | pages={found} stored={stored} | {step} | {age_s}"
            )

    stall_risk = data.get("stall_risk") or []
    print(f"[STALL_RISK] threshold={STALL_GUARD_MINUTES}m warn>{STALL_RISK_MINUTES}m")
    if stall_risk:
        for job in stall_risk:
            slug = job.get("product_slug", "?")
            age = _heartbeat_age_minutes(job, now)
            print(
                f"  ! {slug} ({job.get('status')}) — {age:.0f}m idle "
                f"(stall guard kills at {STALL_GUARD_MINUTES}m)"
            )
    else:
        print("  (none)")

    if progress_deltas:
        print("[PROGRESS_UPDATES]")
        for d in progress_deltas:
            slug = d["slug"]
            if d["kind"] == "finished":
                print(
                    f"  PROGRESS: {slug} finished — final found={d['found']} stored={d['stored']} "
                    f"analysis_done={d['skipped']}"
                )
                continue
            parts = [
                p
                for p in (
                    _format_delta(int(d["delta_found"]), "found"),
                    _format_delta(int(d["delta_stored"]), "stored"),
                    _format_delta(int(d["delta_skipped"]), "analysis"),
                )
                if p
            ]
            change = ", ".join(parts) if parts else f"now {d['status']}"
            print(
                f"  PROGRESS: {slug} {change} — total found={d['found']} stored={d['stored']} "
                f"analysis_done={d['skipped']} ({d['status']})"
            )
    else:
        print("[PROGRESS_UPDATES]")
        print("  (no changes since last check)")

    print(f"[IN_PROGRESS] count={len(data['in_progress'])}")
    for job in data["in_progress"]:
        slug = job.get("product_slug", "?")
        status = job.get("status", "?")
        att = job.get("attempts", 0)
        found = job.get("documents_found", 0)
        stored = job.get("documents_stored", 0)
        skipped = job.get("analyses_skipped", 0)
        reanalyze = job.get("force_reanalyze", False)
        step = _step_summary(job.get("steps"))
        hb = _fmt_ts(job.get("last_heartbeat") or job.get("updated_at"))
        flags = " force_reanalyze" if reanalyze else ""
        print(
            f"  {slug} | {status} att={att} | found={found} stored={stored} "
            f"analysis_skipped={skipped}{flags} | {step} | hb={hb}"
        )
    if not data["in_progress"]:
        print("  (none)")

    print("[RECENT_TERMINAL_15M]")
    for job in data["recent_terminal"]:
        t = _fmt_ts(job.get("completed_at") or job.get("updated_at"))
        err_msg = _format_job_error(job)
        err = f" err={err_msg}" if err_msg else ""
        print(
            f"  {job.get('product_slug')} {job.get('status')}{err} "
            f"found={job.get('documents_found', 0)} stored={job.get('documents_stored', 0)} "
            f"skipped={job.get('analyses_skipped', 0)} at={t}"
        )
    if not data["recent_terminal"]:
        print("  (none)")

    all_alerts = list(data["alerts"])
    print("[ALERTS]")
    if all_alerts:
        for alert in all_alerts:
            print(f"  ALERT: {alert}")
    else:
        print("  ok")

    if log_hits is not None:
        print("[LOG_UNUSUAL]")
        if log_hits:
            for hit in log_hits:
                print(f"  ! {hit}")
        else:
            print("  (none in recent tail)")

    if log_watch is not None:
        print("[LOG_FLEET]")
        if log_watch:
            for hit in log_watch:
                print(f"  > {hit}")
        else:
            print("  (no matching log lines in recent tail)")

    if fix_actions is not None:
        print("[AUTO_FIX]")
        if fix_actions:
            for action in fix_actions:
                print(f"  FIX: {action}")
        else:
            print("  (no action needed)")


async def _run_once(*, include_logs: bool, auto_fix: bool) -> int:
    railway_line, railway_alerts = _railway_crawler_line()
    now = _utc_now()
    data = await _mongo_snapshot()
    data["alerts"] = railway_alerts + data["alerts"]

    memory: dict[str, Any] = {"samples": 0}
    if include_logs:
        log_text = _railway_logs_tail(500)
        memory = _parse_memory_signals(log_text)
        data["alerts"] = data["alerts"] + _memory_alerts(memory)
    data["memory"] = memory

    state = _load_state()
    meta: dict[str, Any] = dict(state.get("meta") or {})
    previous = state.get("jobs") or {}
    if not meta.get("watchdog_started_at"):
        meta["watchdog_started_at"] = now.isoformat()

    track_jobs = data["in_progress"] + data["recent_terminal"] + (data.get("watch_jobs") or [])
    progress_deltas = _progress_deltas(track_jobs, previous)

    fix_actions: list[str] = []
    if auto_fix and data["alerts"]:
        fix_actions = await _auto_fix(data, meta)
        if fix_actions:
            data = await _mongo_snapshot()
            data["alerts"] = railway_alerts + data["alerts"]
            if include_logs:
                log_text = _railway_logs_tail(500)
                memory = _parse_memory_signals(log_text)
                data["alerts"] = data["alerts"] + _memory_alerts(memory)
            data["memory"] = memory
    if auto_fix and memory.get("samples"):
        mem_fixes = _auto_fix_memory(data, meta)
        fix_actions.extend(mem_fixes)

    _save_state(data["in_progress"], meta)

    log_hits = _railway_log_unusual() if include_logs else None
    log_watch = _railway_log_watch() if include_logs else None
    _print_snapshot(
        data,
        railway_line,
        log_hits,
        log_watch=log_watch,
        progress_deltas=progress_deltas,
        now=now,
        fix_actions=fix_actions if auto_fix else None,
    )

    return 2 if data["alerts"] else 0


async def main() -> None:
    parser = argparse.ArgumentParser(description="Crawler/pipeline production monitor")
    parser.add_argument(
        "--logs",
        action="store_true",
        help="Scan recent Railway crawler logs for unusual patterns",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-remediate when alerts fire (requeue, unblock, redeploy with cooldown)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help=f"Run every {LOOP_INTERVAL_SECONDS}s for {WATCHDOG_HOURS}h (implies --logs --fix)",
    )
    args = parser.parse_args()

    include_logs = args.logs or args.loop
    auto_fix = args.fix or args.loop

    if args.loop:
        deadline = time.time() + WATCHDOG_HOURS * 3600
        print(
            f"Watchdog started: interval={LOOP_INTERVAL_SECONDS}s duration={WATCHDOG_HOURS}h "
            f"auto_fix={'on' if auto_fix else 'off'}"
        )
        exit_code = 0
        while time.time() < deadline:
            code = await _run_once(include_logs=include_logs, auto_fix=auto_fix)
            exit_code = max(exit_code, code)
            remaining_h = (deadline - time.time()) / 3600
            print(f"[WATCHDOG] next check in {LOOP_INTERVAL_SECONDS}s (~{remaining_h:.1f}h left)")
            time.sleep(LOOP_INTERVAL_SECONDS)
        print("[WATCHDOG] 24h window complete")
        sys.exit(exit_code)

    sys.exit(await _run_once(include_logs=include_logs, auto_fix=auto_fix))


if __name__ == "__main__":
    asyncio.run(main())
