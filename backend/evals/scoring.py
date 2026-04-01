"""Deterministic scoring functions for the eval harness.

All checks are objective and mechanical -- no LLM-as-judge scoring.
Quality score is a weighted composite of structural compliance metrics.
"""

import re
from typing import Any, Dict, List


def check_required_sections(text: str, required_sections: List[str]) -> Dict[str, Any]:
    """Check presence of required section headings in Stage 3 output."""
    lowered = (text or "").lower()
    results = {}
    for section in required_sections:
        results[section] = section.lower() in lowered
    return {
        "section_results": results,
        "all_present": all(results.values()),
        "present_count": sum(results.values()),
        "total_count": len(required_sections),
    }


def check_ranking_parse(parsed_ranking: List[str], expected_count: int) -> Dict[str, Any]:
    """Check whether Stage 2 ranking was parsed successfully."""
    has_ranking = len(parsed_ranking) > 0
    correct_count = len(parsed_ranking) == expected_count
    all_unique = len(set(parsed_ranking)) == len(parsed_ranking)
    return {
        "has_ranking": has_ranking,
        "correct_count": correct_count,
        "all_unique": all_unique,
        "parsed_count": len(parsed_ranking),
        "expected_count": expected_count,
        "success": has_ranking and correct_count and all_unique,
    }


def check_role_validation(stage1_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Check role section compliance across Stage 1 responses."""
    total = 0
    valid = 0
    for result in stage1_results:
        rv = result.get("role_validation")
        if rv is not None:
            total += 1
            if rv.get("valid"):
                valid += 1
    ratio = valid / total if total > 0 else 0.0
    return {
        "valid": valid,
        "total": total,
        "ratio": round(ratio, 4),
    }


def check_risk_section(stage3_text: str) -> Dict[str, Any]:
    """Check whether Stage 3 contains a non-trivial Risks section."""
    text = stage3_text or ""
    match = re.search(
        r"##\s*Risks(.*?)(##\s*[A-Za-z]|$)", text, flags=re.IGNORECASE | re.DOTALL
    )
    if not match:
        return {"has_risks_section": False, "bullet_count": 0}
    block = match.group(1)
    bullets = [
        line.strip()
        for line in block.splitlines()
        if line.strip().startswith(("-", "*", "1", "2", "3", "4", "5", "6", "7", "8", "9"))
    ]
    return {
        "has_risks_section": True,
        "bullet_count": len(bullets),
    }


def check_rubric_coverage(stage2_text: str, rubric_dimensions: List[Dict[str, str]]) -> Dict[str, Any]:
    """Check whether rubric dimension labels appear in Stage 2 evaluation text."""
    lowered = (stage2_text or "").lower()
    present = {}
    for dim in rubric_dimensions:
        label = dim["label"]
        present[label] = label.lower() in lowered
    covered = sum(present.values())
    total = len(present)
    return {
        "present": present,
        "covered": covered,
        "total": total,
        "ratio": round(covered / total, 4) if total else 1.0,
    }


def compute_quality_score(
    section_check: Dict[str, Any],
    ranking_checks: List[Dict[str, Any]],
    role_check: Dict[str, Any],
    risk_check: Dict[str, Any],
    rubric_checks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute composite quality score from structural checks.

    Weights:
      - Stage 3 required sections:  30%
      - Stage 2 ranking parse rate: 25%
      - Stage 1 role compliance:    20%
      - Risk section quality:       15%
      - Rubric dimension coverage:  10%

    Each component is normalized to 0.0-1.0 before weighting.
    """
    section_score = section_check["present_count"] / max(section_check["total_count"], 1)

    ranking_successes = sum(1 for r in ranking_checks if r.get("success"))
    ranking_score = ranking_successes / max(len(ranking_checks), 1)

    role_score = role_check["ratio"]

    risk_score = min(risk_check["bullet_count"] / 3.0, 1.0) if risk_check["has_risks_section"] else 0.0

    if rubric_checks:
        rubric_avg = sum(r["ratio"] for r in rubric_checks) / len(rubric_checks)
    else:
        rubric_avg = 1.0

    weighted = (
        0.30 * section_score
        + 0.25 * ranking_score
        + 0.20 * role_score
        + 0.15 * risk_score
        + 0.10 * rubric_avg
    )

    return {
        "composite_score": round(weighted, 4),
        "components": {
            "section_score": round(section_score, 4),
            "ranking_parse_score": round(ranking_score, 4),
            "role_compliance_score": round(role_score, 4),
            "risk_section_score": round(risk_score, 4),
            "rubric_coverage_score": round(rubric_avg, 4),
        },
        "weights": {
            "sections": 0.30,
            "ranking_parse": 0.25,
            "role_compliance": 0.20,
            "risk_section": 0.15,
            "rubric_coverage": 0.10,
        },
    }
