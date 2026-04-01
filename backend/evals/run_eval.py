"""Offline evaluation harness for LLM Council.

Runs frozen benchmark prompts through the council pipeline, collects raw
artifacts, and computes Gate 1 pass/fail metrics.

Usage (from project root):
    python -m backend.evals.run_eval [--set dev|holdout|all] [--out <dir>]

Requires a valid OPENROUTER_API_KEY in .env.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on path for relative imports.
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.config import get_profile, COUNCIL_MODELS, CHAIRMAN_MODEL, BACKEND_PORT
from backend.council import (
    run_full_council,
    calculate_aggregate_rankings,
    parse_ranking_from_text,
)
from backend.evals.scoring import (
    check_required_sections,
    check_ranking_parse,
    check_role_validation,
    check_risk_section,
    check_rubric_coverage,
    compute_quality_score,
)

SEED_SET_PATH = Path(__file__).resolve().parent / "seed_set.json"
DEFAULT_OUTPUT_DIR = Path(PROJECT_ROOT) / "data" / "eval_runs"


def _check_backend_port_free() -> None:
    """Abort if the backend port is in use to prevent live-server side effects."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", BACKEND_PORT)) == 0:
            raise RuntimeError(
                f"Port {BACKEND_PORT} is in use (the backend server appears to be running). "
                "Stop the server before running the eval harness to prevent "
                "unintended writes to conversation data."
            )


def load_seed_set() -> Dict[str, Any]:
    with open(SEED_SET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def filter_prompts(
    prompts: List[Dict[str, Any]], target_set: str
) -> List[Dict[str, Any]]:
    if target_set == "all":
        return prompts
    return [p for p in prompts if p.get("set") == target_set]


async def run_single_benchmark(
    prompt: Dict[str, Any],
    council_models: List[str],
    chairman_model: str,
) -> Dict[str, Any]:
    """Run the full council for one benchmark prompt and return raw results."""
    profile_id = prompt["profile_id"]
    profile = get_profile(profile_id)

    run_context = {
        "profile_id": profile_id,
        "profile": profile,
        "packet_id": None,
        "packet_title": None,
        "packet_as_of": None,
        "research_packet": None,
        "role_assignments": [],
    }

    started = time.perf_counter()
    error: Optional[str] = None
    try:
        stage1, stage2, stage3, metadata = await run_full_council(
            prompt["query"],
            interrogation=None,
            run_context=run_context,
            council_models=council_models,
            chairman_model=chairman_model,
        )
    except Exception as exc:
        error = str(exc)
        stage1, stage2, stage3, metadata = [], [], {"model": "error", "response": ""}, {}
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return {
        "prompt_id": prompt["id"],
        "profile_id": profile_id,
        "query": prompt["query"],
        "set": prompt.get("set", "unknown"),
        "elapsed_ms": elapsed_ms,
        "error": error,
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
        "metadata": metadata,
    }


def score_single_result(
    result: Dict[str, Any],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Score one benchmark result against structural checks."""
    stage3_text = (result.get("stage3") or {}).get("response", "")
    required_sections = profile.get("stage3_required_sections", [])
    section_check = check_required_sections(stage3_text, required_sections)

    stage1_results = result.get("stage1", [])
    stage1_count = len(stage1_results)
    ranking_checks = []
    rubric_checks = []
    for s2 in result.get("stage2", []):
        parsed = s2.get("parsed_ranking", [])
        ranking_checks.append(check_ranking_parse(parsed, stage1_count))
        rubric_checks.append(
            check_rubric_coverage(
                s2.get("ranking", ""),
                profile.get("rubric_dimensions", []),
            )
        )

    role_check = check_role_validation(stage1_results)
    risk_check = check_risk_section(stage3_text)

    quality = compute_quality_score(
        section_check, ranking_checks, role_check, risk_check, rubric_checks
    )

    return {
        "prompt_id": result["prompt_id"],
        "section_check": section_check,
        "ranking_checks": ranking_checks,
        "role_check": role_check,
        "risk_check": risk_check,
        "rubric_checks": rubric_checks,
        "quality": quality,
    }


def evaluate_gate(
    scores: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    baseline_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Evaluate Gate 1 pass/fail criteria."""
    total = len(results)
    crashes = sum(1 for r in results if r.get("error") is not None)
    crash_free = crashes == 0

    sections_pass_count = sum(
        1 for s in scores if s["section_check"]["all_present"]
    )
    sections_pass = sections_pass_count == total

    all_ranking_checks = []
    for s in scores:
        all_ranking_checks.extend(s.get("ranking_checks", []))
    ranking_successes = sum(1 for r in all_ranking_checks if r.get("success"))
    ranking_total = len(all_ranking_checks)
    ranking_rate = ranking_successes / max(ranking_total, 1)
    ranking_pass = ranking_rate >= 0.95

    quality_scores = [s["quality"]["composite_score"] for s in scores]
    mean_quality = sum(quality_scores) / max(len(quality_scores), 1)

    if baseline_score is not None and baseline_score > 0:
        quality_delta = (mean_quality - baseline_score) / baseline_score
    else:
        quality_delta = None

    quality_uplift_pass = (
        quality_delta is not None and quality_delta >= 0.10
    ) if baseline_score is not None else True

    holdout_scores = [
        s["quality"]["composite_score"]
        for s, r in zip(scores, results)
        if r.get("set") == "holdout"
    ]
    holdout_mean = sum(holdout_scores) / max(len(holdout_scores), 1) if holdout_scores else None

    holdout_pass = True
    if holdout_mean is not None and baseline_score is not None:
        holdout_pass = holdout_mean >= baseline_score

    all_pass = all([crash_free, sections_pass, ranking_pass, quality_uplift_pass, holdout_pass])

    return {
        "pass": all_pass,
        "checks": {
            "crash_free": {
                "pass": crash_free,
                "crashes": crashes,
                "total": total,
            },
            "sections_present": {
                "pass": sections_pass,
                "passing": sections_pass_count,
                "total": total,
            },
            "ranking_parse": {
                "pass": ranking_pass,
                "rate": round(ranking_rate, 4),
                "successes": ranking_successes,
                "total": ranking_total,
            },
            "quality_uplift": {
                "pass": quality_uplift_pass,
                "mean_quality": round(mean_quality, 4),
                "baseline_score": baseline_score,
                "delta": round(quality_delta, 4) if quality_delta is not None else None,
            },
            "holdout_no_regression": {
                "pass": holdout_pass,
                "holdout_mean": round(holdout_mean, 4) if holdout_mean is not None else None,
                "baseline_score": baseline_score,
            },
        },
    }


async def run_eval(
    target_set: str = "all",
    output_dir: Optional[str] = None,
    baseline_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full eval harness and produce artifacts."""
    _check_backend_port_free()
    seed_data = load_seed_set()
    prompts = filter_prompts(seed_data["prompts"], target_set)
    if not prompts:
        raise ValueError(f"No prompts found for set '{target_set}'")

    seed_hash = file_sha256(SEED_SET_PATH)
    council_models = COUNCIL_MODELS
    chairman_model = CHAIRMAN_MODEL

    print(f"Eval harness: running {len(prompts)} prompts (set={target_set})")
    print(f"Seed set hash: {seed_hash}")
    print(f"Council models: {council_models}")
    print(f"Chairman: {chairman_model}")
    print()

    results = []
    for idx, prompt in enumerate(prompts):
        label = f"[{idx + 1}/{len(prompts)}] {prompt['id']} ({prompt['profile_id']})"
        print(f"  Running {label}...", flush=True)
        result = await run_single_benchmark(prompt, council_models, chairman_model)
        status = "OK" if result["error"] is None else f"ERROR: {result['error']}"
        print(f"  {label} -> {status} ({result['elapsed_ms']}ms)")
        results.append(result)

    print()
    print("Scoring results...")
    scores = []
    for result in results:
        profile = get_profile(result["profile_id"])
        scores.append(score_single_result(result, profile))

    baseline_score = None
    if baseline_file and os.path.exists(baseline_file):
        with open(baseline_file, "r", encoding="utf-8") as f:
            baseline_data = json.load(f)
        baseline_score = baseline_data.get("summary", {}).get("mean_quality_score")
        print(f"Loaded baseline score: {baseline_score}")

    gate = evaluate_gate(scores, results, baseline_score=baseline_score)

    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "target_set": target_set,
        "prompt_count": len(prompts),
        "seed_set_hash": seed_hash,
        "council_models": council_models,
        "chairman_model": chairman_model,
        "mean_quality_score": round(
            sum(s["quality"]["composite_score"] for s in scores) / max(len(scores), 1),
            4,
        ),
        "gate": gate,
    }

    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out_dir / f"eval_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    with open(run_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    with open(run_dir / "scores.json", "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2, default=str)

    serializable_results = []
    for r in results:
        sr = dict(r)
        sr.pop("stage1", None)
        sr.pop("stage2", None)
        sr["stage3_response"] = (r.get("stage3") or {}).get("response", "")[:2000]
        sr["stage3_model"] = (r.get("stage3") or {}).get("model", "")
        serializable_results.append(sr)
    with open(run_dir / "results_lite.json", "w", encoding="utf-8") as f:
        json.dump(serializable_results, f, indent=2, default=str)

    gate_status = "PASS" if gate["pass"] else "FAIL"
    report_lines = [
        f"# Eval Run Report",
        f"",
        f"- Run At: {summary['run_at']}",
        f"- Target Set: {target_set}",
        f"- Prompts: {len(prompts)}",
        f"- Seed Set Hash: `{seed_hash}`",
        f"- Council Models: {', '.join(council_models)}",
        f"- Chairman: {chairman_model}",
        f"- Mean Quality Score: {summary['mean_quality_score']}",
        f"",
        f"## Gate Result: **{gate_status}**",
        f"",
    ]
    for check_name, check_data in gate["checks"].items():
        status = "PASS" if check_data["pass"] else "FAIL"
        report_lines.append(f"- {check_name}: **{status}** {json.dumps({k: v for k, v in check_data.items() if k != 'pass'})}")
    report_lines.append("")

    report_lines.append("## Per-Prompt Scores")
    report_lines.append("")
    for score in scores:
        q = score["quality"]
        report_lines.append(
            f"- `{score['prompt_id']}`: composite={q['composite_score']}"
        )

    with open(run_dir / "report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    print()
    print(f"Gate Result: {gate_status}")
    for check_name, check_data in gate["checks"].items():
        status = "PASS" if check_data["pass"] else "FAIL"
        print(f"  {check_name}: {status}")
    print()
    print(f"Artifacts saved to: {run_dir}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="LLM Council Eval Harness")
    parser.add_argument(
        "--set",
        choices=["dev", "holdout", "all"],
        default="all",
        help="Which prompt subset to evaluate (default: all)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory for artifacts (default: data/eval_runs/)",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="Path to a previous summary.json to use as baseline for quality comparison",
    )
    args = parser.parse_args()
    asyncio.run(run_eval(target_set=args.set, output_dir=args.out, baseline_file=args.baseline))


if __name__ == "__main__":
    main()
