#!/usr/bin/env python3
"""Benchmark escalation vs. nano-only baseline across a sample corpus.

Usage:
    uv run python scripts/benchmark_pipeline.py --corpus path/to/docs/ --sample 100
    uv run python scripts/benchmark_pipeline.py --corpus path/to/docs/ --baseline

With --baseline, all LLM calls are forced to ["gpt-5-nano"] (no escalation).
Without --baseline, normal escalation routing applies.

Output: benchmark_results_<mode>_<timestamp>.csv + summary to stdout.
"""

import argparse
import asyncio
import csv
import json
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.analyser import analyse_document  # noqa: E402
from src.models.document import Document  # noqa: E402
from src.services.extraction_service import extract_document_facts  # noqa: E402
from src.utils.llm_usage import UsageTracker, usage_tracking  # noqa: E402

_NANO_ONLY: list[str] = ["gpt-5-nano"]

_escalation_count = 0
_call_count = 0


@asynccontextmanager
async def _count_escalations():
    """Wraps acompletion_with_escalation to count escalation events."""
    global _escalation_count, _call_count
    _escalation_count = 0
    _call_count = 0

    from src.llm import _extract_json_from_response, acompletion_with_fallback

    async def _tracked(messages, primary, escalation, validator, **kwargs):
        global _escalation_count, _call_count
        _call_count += 1
        resp = await acompletion_with_fallback(messages, model_priority=primary, **kwargs)
        try:
            content = _extract_json_from_response(resp)
            should_escalate = not validator(content)
        except ValueError:
            should_escalate = True
        if should_escalate:
            _escalation_count += 1
            resp = await acompletion_with_fallback(messages, model_priority=escalation, **kwargs)
        return resp

    with (
        patch("src.llm.acompletion_with_escalation", side_effect=_tracked),
        patch("src.services.extraction_service.acompletion_with_escalation", side_effect=_tracked),
        patch("src.analyser.acompletion_with_escalation", side_effect=_tracked),
    ):
        yield


@asynccontextmanager
async def _force_nano():
    """Forces all LLM calls (fallback + escalation) to gpt-5-nano."""
    from src.llm import acompletion_with_fallback as _orig_fb

    async def _nano_fb(messages, model_priority=None, **kwargs):
        return await _orig_fb(messages, model_priority=_NANO_ONLY, **kwargs)

    async def _nano_esc(messages, primary, escalation, validator, **kwargs):
        return await _orig_fb(messages, model_priority=_NANO_ONLY, **kwargs)

    with (
        patch("src.llm.acompletion_with_fallback", side_effect=_nano_fb),
        patch("src.services.extraction_service.acompletion_with_fallback", side_effect=_nano_fb),
        patch("src.services.extraction_service.acompletion_with_escalation", side_effect=_nano_esc),
        patch("src.analyser.acompletion_with_fallback", side_effect=_nano_fb),
        patch("src.analyser.acompletion_with_escalation", side_effect=_nano_esc),
    ):
        yield


async def _run_doc(doc: Document, baseline: bool) -> dict[str, Any]:
    start = time.time()
    tracker = UsageTracker()
    callback = tracker.create_tracker("benchmark")

    ctx = _force_nano() if baseline else _count_escalations()

    try:
        async with ctx:
            async with usage_tracking(callback):
                await extract_document_facts(doc, use_cache=False)
                await analyse_document(doc, use_cache=False)
    except Exception as e:
        return {
            "doc_id": doc.id,
            "doc_type": doc.doc_type,
            "text_length": len(doc.text or ""),
            "models_used": "",
            "call_count": 0,
            "escalation_count": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "duration_s": round(time.time() - start, 2),
            "error": str(e),
        }

    summary = tracker.get_summary()
    total_cost = sum(v.get("cost") or 0.0 for v in summary.values())
    total_tokens = sum(v["total_tokens"] for v in summary.values())

    return {
        "doc_id": doc.id,
        "doc_type": doc.doc_type,
        "text_length": len(doc.text or ""),
        "models_used": "|".join(summary.keys()),
        "call_count": _call_count,
        "escalation_count": 0 if baseline else _escalation_count,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(total_cost, 6),
        "duration_s": round(time.time() - start, 2),
        "error": None,
    }


def _load_docs(corpus_path: Path, sample: int) -> list[Document]:
    docs = []
    for f in sorted(corpus_path.glob("*.json"))[:sample]:
        try:
            data = json.loads(f.read_text())
            docs.append(Document(**data))
        except Exception as e:
            print(f"  Skip {f.name}: {e}")
    return docs


async def main() -> None:
    parser = argparse.ArgumentParser(description="LLM escalation benchmark")
    parser.add_argument("--corpus", required=True, help="Directory of document JSON files")
    parser.add_argument("--sample", type=int, default=100, help="Max documents to process")
    parser.add_argument("--baseline", action="store_true", help="Force gpt-5-nano for all calls")
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    if not corpus_path.is_dir():
        print(f"Error: {corpus_path} is not a directory")
        sys.exit(1)

    docs = _load_docs(corpus_path, args.sample)
    if not docs:
        print("No documents found.")
        sys.exit(1)

    mode = "baseline (nano-only)" if args.baseline else "escalation"
    print(f"Running {mode} benchmark on {len(docs)} documents...")

    results = []
    for i, doc in enumerate(docs, 1):
        print(f"  [{i}/{len(docs)}] {doc.id} ({doc.doc_type})")
        result = await _run_doc(doc, baseline=args.baseline)
        results.append(result)
        if result["error"]:
            print(f"    ERROR: {result['error']}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_tag = "baseline" if args.baseline else "escalation"
    out_path = Path(f"benchmark_results_{mode_tag}_{timestamp}.csv")

    with open(out_path, "w", newline="") as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)

    successful = [r for r in results if not r.get("error")]
    total_cost = sum(r["estimated_cost_usd"] for r in successful)
    total_escalations = sum(r["escalation_count"] for r in successful)
    avg_cost = total_cost / len(successful) if successful else 0
    total_calls = sum(r["call_count"] for r in successful)
    escalation_rate = total_escalations / max(total_calls, 1) * 100

    print(f"\n{'=' * 50}")
    print(f"Mode:              {mode}")
    print(f"Documents:         {len(successful)}/{len(docs)} succeeded")
    print(f"Total cost:        ${total_cost:.4f}")
    print(f"Avg cost/doc:      ${avg_cost:.4f}")
    print(f"Total escalations: {total_escalations}")
    print(f"Results saved to:  {out_path}")
    print(f"{'=' * 50}")
    print("\nAcceptance targets:")
    print(f"  Total LLM calls:   {total_calls}")
    print(f"  Escalation rate < 30%: {escalation_rate:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
