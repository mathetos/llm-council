"""Generate a CSV report card for strict-free model selection."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import OPENROUTER_API_KEY, OPENROUTER_API_URL  # noqa: E402
from backend.openrouter import (  # noqa: E402
    list_models_with_error,
    list_user_visible_models_with_error,
)


def _safe_float(value: Any) -> Optional[float]:
    """Parse numeric-ish values while handling nulls/non-numeric strings."""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _is_strict_zero_cost_free_model(model: Dict[str, Any]) -> bool:
    """Match explicit :free variants priced at <= 0 across pricing fields."""
    model_id = (model.get("id") or "").strip()
    if not model_id.endswith(":free"):
        return False
    if model_id == "openrouter/free":
        return False

    pricing = model.get("pricing") or {}
    if not isinstance(pricing, dict):
        return False
    numeric_prices = [_safe_float(value) for value in pricing.values()]
    numeric_prices = [value for value in numeric_prices if value is not None]
    return bool(numeric_prices) and max(numeric_prices) <= 0.0


def _classify_recommended_role(model_id: str, context_length: Optional[int]) -> str:
    """Heuristic role fit for this codebase's council stages."""
    lower = (model_id or "").lower()
    if "openrouter/free" in lower:
        return "Router Primary (fallback diversification)"
    if "nano" in lower or "3b" in lower or "4b" in lower:
        return "Stage1 Execution Operator"
    if any(token in lower for token in ("70b", "80b", "120b", "405b")):
        return "Stage1 Reasoning Challenger"
    if context_length and context_length >= 200_000:
        return "Interrogator / Long-Context Analyst"
    return "Stage1 Generalist"


async def _probe_model(
    client: httpx.AsyncClient,
    model_id: str,
    *,
    timeout_seconds: float,
    privacy_mode: bool,
) -> Dict[str, Any]:
    """
    Probe model with a tiny prompt.

    privacy_mode=True applies provider constraints:
    - data_collection: deny
    - zdr: true
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply exactly: OK"}],
        "max_tokens": 8,
        "temperature": 0,
    }
    if privacy_mode:
        payload["provider"] = {
            "data_collection": "deny",
            "zdr": True,
        }

    started = time.perf_counter()
    try:
        response = await client.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            detail = _summarize_error(response)
            return {
                "status": "fail",
                "latency_ms": latency_ms,
                "routed_model": None,
                "error": detail,
            }
        data = response.json()
        return {
            "status": "pass",
            "latency_ms": latency_ms,
            "routed_model": data.get("model"),
            "error": None,
        }
    except httpx.TimeoutException as e:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "status": "fail",
            "latency_ms": latency_ms,
            "routed_model": None,
            "error": f"Timeout: {e}",
        }
    except httpx.RequestError as e:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "status": "fail",
            "latency_ms": latency_ms,
            "routed_model": None,
            "error": f"Network error: {e}",
        }


def _summarize_error(response: httpx.Response) -> str:
    """Extract compact, filter-friendly error text from OpenRouter responses."""
    prefix = f"HTTP {response.status_code}"
    try:
        payload = response.json()
        error = payload.get("error") or {}
        message = (error.get("message") or "").strip()
        code = error.get("code")
        metadata = error.get("metadata") or {}
        provider_name = metadata.get("provider_name") or ""
        raw = (metadata.get("raw") or "").strip().replace("\n", " ")
        if len(raw) > 240:
            raw = f"{raw[:240]}..."

        parts: List[str] = [prefix]
        if code is not None:
            parts.append(f"code={code}")
        if message:
            parts.append(f"message={message}")
        if provider_name:
            parts.append(f"provider={provider_name}")
        if raw:
            parts.append(f"raw={raw}")
        return " | ".join(parts)
    except Exception:  # noqa: BLE001
        text = (response.text or "").strip().replace("\n", " ")
        if len(text) > 320:
            text = f"{text[:320]}..."
        return f"{prefix} | {text}"


async def _evaluate_model(
    model_id: str,
    model_meta: Optional[Dict[str, Any]],
    visible_set: set,
    *,
    timeout_seconds: float,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """Evaluate one model for baseline and privacy-constrained routing."""
    pricing = (model_meta or {}).get("pricing") or {}
    prompt_price = _safe_float(pricing.get("prompt"))
    completion_price = _safe_float(pricing.get("completion"))
    context_length = (model_meta or {}).get("context_length")
    supported_parameters = (model_meta or {}).get("supported_parameters") or []

    async with semaphore:
        async with httpx.AsyncClient() as client:
            baseline = await _probe_model(
                client,
                model_id,
                timeout_seconds=timeout_seconds,
                privacy_mode=False,
            )
            privacy = await _probe_model(
                client,
                model_id,
                timeout_seconds=timeout_seconds,
                privacy_mode=True,
            )

    privacy_fit = (
        "privacy_ok"
        if privacy["status"] == "pass"
        else "not_privacy_safe_for_sensitive_prompts"
    )

    return {
        "model_id": model_id,
        "family": model_id.split("/", 1)[0] if "/" in model_id else model_id,
        "eligible_now": model_id in visible_set,
        "strict_zero_cost": _is_strict_zero_cost_free_model(model_meta or {}),
        "context_length": context_length,
        "prompt_price_per_m": prompt_price,
        "completion_price_per_m": completion_price,
        "supports_tools": "tools" in supported_parameters,
        "baseline_status": baseline["status"],
        "baseline_latency_ms": baseline["latency_ms"],
        "baseline_routed_model": baseline["routed_model"],
        "baseline_error": baseline["error"],
        "privacy_status": privacy["status"],
        "privacy_latency_ms": privacy["latency_ms"],
        "privacy_routed_model": privacy["routed_model"],
        "privacy_error": privacy["error"],
        "privacy_fit": privacy_fit,
        "recommended_role": _classify_recommended_role(model_id, context_length),
    }


async def _generate_report(
    output_path: Path,
    *,
    timeout_seconds: float,
    concurrency: int,
    include_router_row: bool,
) -> Tuple[int, int]:
    """Build rows and write CSV. Returns (row_count, privacy_pass_count)."""
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.strip():
        raise RuntimeError("OPENROUTER_API_KEY is missing or empty in .env")

    all_models, all_models_err = await list_models_with_error()
    if all_models is None:
        raise RuntimeError(f"Unable to load /models: {all_models_err}")
    visible_models, visible_err = await list_user_visible_models_with_error()
    if visible_models is None:
        raise RuntimeError(f"Unable to load /models/user: {visible_err}")

    by_id = {item.get("id"): item for item in all_models if item.get("id")}
    visible_set = set(visible_models)

    strict_free_ids = sorted(
        [
            model.get("id")
            for model in all_models
            if model.get("id") and _is_strict_zero_cost_free_model(model)
        ]
    )
    candidate_ids = list(strict_free_ids)
    if include_router_row and "openrouter/free" in visible_set:
        candidate_ids.append("openrouter/free")

    semaphore = asyncio.Semaphore(max(1, concurrency))
    tasks = [
        _evaluate_model(
            model_id,
            by_id.get(model_id),
            visible_set,
            timeout_seconds=timeout_seconds,
            semaphore=semaphore,
        )
        for model_id in candidate_ids
    ]
    rows = await asyncio.gather(*tasks)

    rows.sort(
        key=lambda row: (
            0 if row["privacy_status"] == "pass" else 1,
            0 if row["eligible_now"] else 1,
            -(row["context_length"] or 0),
            row["model_id"],
        )
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "model_id",
        "family",
        "eligible_now",
        "strict_zero_cost",
        "context_length",
        "prompt_price_per_m",
        "completion_price_per_m",
        "supports_tools",
        "baseline_status",
        "baseline_latency_ms",
        "baseline_routed_model",
        "baseline_error",
        "privacy_status",
        "privacy_latency_ms",
        "privacy_routed_model",
        "privacy_error",
        "privacy_fit",
        "recommended_role",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    privacy_pass_count = sum(1 for row in rows if row["privacy_status"] == "pass")
    return len(rows), privacy_pass_count


def _default_output_path() -> Path:
    """Construct timestamped output file path under data/reports."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    return ROOT / "data" / "reports" / f"free_model_report_card-{timestamp}.csv"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate free model report card CSV.")
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional output CSV path (default: data/reports timestamped file).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=20.0,
        help="Per-request timeout for probe calls.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Concurrent model probes.",
    )
    parser.add_argument(
        "--no-router-row",
        action="store_true",
        help="Do not include openrouter/free as a separate row.",
    )
    return parser.parse_args()


async def _main_async() -> int:
    args = parse_args()
    output_path = Path(args.output).resolve() if args.output else _default_output_path()
    row_count, privacy_pass_count = await _generate_report(
        output_path,
        timeout_seconds=args.timeout_seconds,
        concurrency=args.concurrency,
        include_router_row=not args.no_router_row,
    )
    summary = {
        "output_csv": str(output_path),
        "rows_written": row_count,
        "privacy_pass_rows": privacy_pass_count,
    }
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    """Program entrypoint."""
    try:
        return asyncio.run(_main_async())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
