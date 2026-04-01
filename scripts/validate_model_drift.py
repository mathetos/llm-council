"""Validate pairing model drift against OpenRouter /models and /models/user."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import MODEL_PAIRINGS  # noqa: E402
from backend.openrouter import (  # noqa: E402
    list_models_with_error,
    list_user_visible_models_with_error,
)


async def _run() -> int:
    all_models, all_models_err = await list_models_with_error()
    visible_models, visible_err = await list_user_visible_models_with_error()

    if all_models is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "failed_all_models",
                    "detail": all_models_err,
                },
                indent=2,
            )
        )
        return 2

    if visible_models is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "failed_visible_models",
                    "detail": visible_err,
                },
                indent=2,
            )
        )
        return 2

    catalog_ids = {m.get("id") for m in all_models if isinstance(m, dict) and m.get("id")}
    visible_ids = set(visible_models)

    report = []
    has_missing = False
    has_filtered = False

    for pairing_id, pairing in MODEL_PAIRINGS.items():
        models = list(
            dict.fromkeys(
                list(pairing["council_models"])
                + [pairing["chairman_model"], pairing["interrogator_model"]]
            )
        )
        missing = [m for m in models if m not in catalog_ids]
        filtered = [m for m in models if m in catalog_ids and m not in visible_ids]
        has_missing = has_missing or bool(missing)
        has_filtered = has_filtered or bool(filtered)
        report.append(
            {
                "pairing_id": pairing_id,
                "missing_from_catalog": missing,
                "filtered_for_key": filtered,
            }
        )

    result = {
        "ok": not (has_missing or has_filtered),
        "has_missing": has_missing,
        "has_filtered": has_filtered,
        "pairings": report,
    }
    print(json.dumps(result, indent=2))
    if has_missing:
        return 3
    if has_filtered:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
