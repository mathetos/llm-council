# LLM Council Eval Harness

Offline evaluation harness for measuring council output quality with frozen benchmark prompts.

## Quick Start

From the project root with a valid `.env`:

```bash
# Run all 30 benchmarks (dev + holdout)
python -m backend.evals.run_eval

# Run only the dev set (24 prompts)
python -m backend.evals.run_eval --set dev

# Run only the holdout set (6 prompts)
python -m backend.evals.run_eval --set holdout

# Compare against a saved baseline
python -m backend.evals.run_eval --baseline data/eval_runs/eval_BASELINE/summary.json
```

## How It Works

1. Loads `seed_set.json` (frozen benchmark prompts, 10 per domain).
2. Runs each prompt through `run_full_council()` with the configured model pairing.
3. Scores each result using deterministic structural checks (no LLM-as-judge).
4. Evaluates Gate 1 pass/fail criteria.
5. Writes artifacts to `data/eval_runs/eval_<timestamp>/`.

## Seed Set

- 30 prompts total: 10 marketing, 10 product_development, 10 business_development.
- 24 in the `dev` set (used during development), 6 in `holdout` (for final gate only).
- **Do not edit `seed_set.json` after freeze.** Verify integrity via the SHA-256 hash printed at run start.

## Artifacts

Each run produces:

| File | Contents |
|------|----------|
| `summary.json` | Run metadata, mean quality score, gate pass/fail |
| `scores.json` | Per-prompt scoring detail |
| `results_lite.json` | Truncated raw results (stage3 text capped at 2000 chars) |
| `report.md` | Human-readable report with gate status and per-prompt scores |

## Quality Score

Composite score (0.0 - 1.0) based on weighted structural checks:

| Component | Weight | What It Measures |
|-----------|--------|-----------------|
| Stage 3 required sections | 30% | All profile-required headings present |
| Stage 2 ranking parse | 25% | Rankings extracted correctly |
| Stage 1 role compliance | 20% | Role card sections present in responses |
| Risk section depth | 15% | Non-trivial risk bullets in Stage 3 |
| Rubric dimension coverage | 10% | Rubric labels mentioned in evaluations |

## Gate 1 Criteria

All must pass:

1. 100% crash-free execution
2. 100% Stage 3 required sections present
3. Stage 2 ranking parse success >= 95%
4. Mean quality score >= 10% uplift over baseline (when baseline provided)
5. Holdout set quality >= baseline (no regression)
