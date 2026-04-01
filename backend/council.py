"""3-stage LLM Council orchestration."""

import asyncio
import re
import time
from typing import List, Dict, Any, Tuple, Optional, Callable, Awaitable
from .openrouter import query_models_parallel, query_model, query_model_with_error
from .config import (
    COUNCIL_MODELS,
    CHAIRMAN_MODEL,
    DEFAULT_PROFILE_ID,
    GUARDRAIL_ENFORCEMENT_MODE,
    GUARDRAIL_THRESHOLDS,
    INTERROGATOR_MODEL,
    INTERROGATOR_MIN_QUESTIONS,
    INTERROGATOR_MAX_QUESTIONS,
    get_profile,
)

DEFER_ANSWER_SENTINEL = "__DEFER_TO_COUNCIL__"
DEFER_ANSWER_ALIASES = {
    DEFER_ANSWER_SENTINEL.lower(),
    "defer",
    "defer to council",
    "unsure",
    "not sure",
    "i dont know",
    "i don't know",
}

ProgressCallback = Callable[[Dict[str, Any]], Awaitable[None]]


def is_defer_answer(answer: str) -> bool:
    """Return True when the user explicitly defers an aspect to the council."""
    normalized = (answer or "").strip().lower()
    return normalized in DEFER_ANSWER_ALIASES


def _interrogation_steps_text(steps: List[Dict[str, Any]]) -> str:
    """Format interrogation transcript lines for prompts."""
    lines: List[str] = []
    for idx, step in enumerate(steps, start=1):
        answer = step.get("answer", "").strip()
        if step.get("deferred"):
            answer = "[User deferred this aspect to the council]"
        lines.append(f"Q{idx}: {step.get('question', '').strip()}")
        lines.append(f"A{idx}: {answer}")
    return "\n".join(lines).strip()


def _extract_single_question(raw_text: str) -> str:
    """Extract a single usable question from model output."""
    cleaned = (raw_text or "").strip()
    if not cleaned:
        return ""

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""

    first = lines[0]
    if first.lower().startswith("question:"):
        first = first.split(":", 1)[1].strip()
    if not first.endswith("?"):
        first = f"{first.rstrip('.') }?"
    return first


async def generate_interrogator_question(
    user_query: str,
    steps: List[Dict[str, Any]],
    run_context: Optional[Dict[str, Any]] = None,
    *,
    min_questions: int = INTERROGATOR_MIN_QUESTIONS,
    max_questions: int = INTERROGATOR_MAX_QUESTIONS,
    interrogator_model: str = INTERROGATOR_MODEL,
) -> Tuple[str, Optional[str]]:
    """
    Ask the interrogator model for the next single clarifying question.

    Returns:
        (question_text, error_message_or_none)
    """
    asked = len(steps)
    transcript = _interrogation_steps_text(steps) or "(no prior questions)"
    profile = (run_context or {}).get("profile")
    packet = (run_context or {}).get("research_packet")
    profile_context = ""
    if profile:
        required = ", ".join(profile.get("required_context_fields", []))
        profile_context = (
            f"Selected profile: {profile.get('name', profile.get('id', 'unknown'))}\n"
            f"Required context fields to uncover: {required or '(none specified)'}\n"
        )
    packet_context = format_research_packet_context(packet)
    packet_context = packet_context if packet_context else "(no research packet provided)"

    prompt = f"""You are the Interrogator for an LLM Council.
Your job is to ask exactly ONE clarifying question at a time to improve final answer quality.

Rules:
- Ask only one question.
- Keep it concise and high-information.
- Prefer unresolved constraints, goals, audience, timeline, and success criteria.
- The user may defer an aspect to the council; if so, ask about another critical unknown.
- Current question count: {asked}. Target range for this run: {min_questions} to {max_questions}.
- Output only the question text, nothing else.

Profile and packet context:
{profile_context}
{packet_context}

Original user query:
{user_query}

Interrogation transcript so far:
{transcript}
"""

    response, err = await query_model_with_error(
        interrogator_model,
        [{"role": "user", "content": prompt}],
        timeout=60.0,
    )
    if response is None:
        fallback = "What outcome would make this verdict most useful to you?"
        return fallback, err

    question = _extract_single_question(response.get("content") or "")
    if not question:
        return "What is the most important constraint we should respect?", "Empty interrogator question"
    return question, None


async def should_continue_interrogation(
    user_query: str,
    steps: List[Dict[str, Any]],
    *,
    min_questions: int = INTERROGATOR_MIN_QUESTIONS,
    max_questions: int = INTERROGATOR_MAX_QUESTIONS,
    interrogator_model: str = INTERROGATOR_MODEL,
) -> Tuple[bool, Optional[str]]:
    """
    Decide whether another interrogator question is needed.

    Returns:
        (should_ask_next, error_message_or_none)
    """
    asked = len(steps)
    if asked < min_questions:
        return True, None
    if asked >= max_questions:
        return False, None

    transcript = _interrogation_steps_text(steps)
    prompt = f"""Decide if one more clarifying question is needed.
Reply with EXACTLY one token on the first line: ASK_NEXT or STOP.

Question count: {asked}
Min required: {min_questions}
Max allowed: {max_questions}

Original query:
{user_query}

Transcript:
{transcript}
"""

    response, err = await query_model_with_error(
        interrogator_model,
        [{"role": "user", "content": prompt}],
        timeout=45.0,
    )
    if response is None:
        # Conservative default after minimum is reached: stop instead of over-questioning.
        return False, err

    decision = (response.get("content") or "").strip().upper()
    return decision.startswith("ASK_NEXT"), None


async def summarize_interrogation(
    user_query: str,
    steps: List[Dict[str, Any]],
    *,
    interrogator_model: str = INTERROGATOR_MODEL,
) -> str:
    """Generate a concise summary of interrogation findings."""
    transcript = _interrogation_steps_text(steps)
    prompt = f"""Summarize the interrogation context for downstream models.
Provide 3-6 concise bullet points covering goals, constraints, unknowns, and any deferred aspects.

Original query:
{user_query}

Transcript:
{transcript}
"""

    response, _ = await query_model_with_error(
        interrogator_model,
        [{"role": "user", "content": prompt}],
        timeout=45.0,
    )
    if response is not None:
        summary = (response.get("content") or "").strip()
        if summary:
            return summary

    # Deterministic fallback summary if the model call fails.
    bullet_lines = []
    for idx, step in enumerate(steps, start=1):
        answer = "[Deferred to council]" if step.get("deferred") else step.get("answer", "")
        bullet_lines.append(f"- Q{idx}: {step.get('question', '').strip()}")
        bullet_lines.append(f"  - A{idx}: {answer.strip()}")
    return "\n".join(bullet_lines)


def format_interrogation_context(interrogation: Optional[Dict[str, Any]]) -> str:
    """Create a plain-text context block for Stage 1 prompts."""
    if not interrogation or not interrogation.get("completed"):
        return ""

    summary = (interrogation.get("summary") or "").strip()
    steps = interrogation.get("steps") or []
    transcript = _interrogation_steps_text(steps)

    sections = []
    if summary:
        sections.append("Interrogator Summary:\n" + summary)
    if transcript:
        sections.append("Interrogation Transcript:\n" + transcript)
    return "\n\n".join(sections).strip()


def format_research_packet_context(packet: Optional[Dict[str, Any]]) -> str:
    """Create plain-text research packet context."""
    if not packet:
        return ""

    facts = packet.get("facts", [])
    fact_lines = []
    for fact in facts:
        statement = fact.get("statement", "").strip()
        confidence = fact.get("confidence", "unknown")
        source = fact.get("source")
        source_part = f" (source: {source})" if source else ""
        fact_lines.append(f"- [{confidence}] {statement}{source_part}")

    assumptions = packet.get("assumptions", [])
    constraints = packet.get("constraints", [])
    open_questions = packet.get("open_questions", [])

    sections = [
        f"Research Packet: {packet.get('title', 'Untitled')} ({packet.get('packet_id', 'unknown')})",
        f"As of: {packet.get('as_of', 'unknown')}",
        "",
        "Summary:",
        packet.get("summary", "").strip(),
        "",
        "Facts:",
        "\n".join(fact_lines) if fact_lines else "- (none provided)",
        "",
        "Assumptions:",
        "\n".join(f"- {item}" for item in assumptions) if assumptions else "- (none provided)",
        "",
        "Constraints:",
        "\n".join(f"- {item}" for item in constraints) if constraints else "- (none provided)",
        "",
        "Open Questions:",
        "\n".join(f"- {item}" for item in open_questions) if open_questions else "- (none provided)",
    ]
    return "\n".join(sections).strip()


def assign_perspective_roles(
    models: List[str],
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Assign one role card per model, cycling only if models exceed available roles."""
    roles = profile.get("perspective_roles", [])
    assignments: List[Dict[str, Any]] = []
    for idx, model in enumerate(models):
        role = roles[idx % len(roles)]
        assignments.append(
            {
                "model": model,
                "role_id": role["id"],
                "role_name": role["name"],
                "mandate": role["mandate"],
                "must_include": role["must_include"],
            }
        )
    return assignments


def resolve_perspective_roles(
    models: List[str],
    profile: Dict[str, Any],
    overrides: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Resolve role assignments with unique auto-fill defaults and optional overrides.

    Rules:
    - Unknown role ids or models raise ValueError.
    - Missing roles auto-fill using unique models when possible.
    - Duplicate model assignments are allowed but surfaced as warnings.
    """
    role_cards = profile.get("perspective_roles", [])
    valid_role_ids = {role["id"] for role in role_cards}
    overrides = overrides or {}

    unknown_roles = sorted(set(overrides.keys()) - valid_role_ids)
    if unknown_roles:
        raise ValueError(f"Unknown role ids in override: {', '.join(unknown_roles)}")

    unknown_models = sorted({model for model in overrides.values() if model not in models})
    if unknown_models:
        raise ValueError(
            "Override includes model(s) not in selected pairing: "
            + ", ".join(unknown_models)
        )

    assignments: List[Dict[str, Any]] = []
    used_models: set = set()
    model_idx = 0

    for role in role_cards:
        role_id = role["id"]
        assigned_model = overrides.get(role_id)
        if assigned_model is None:
            available = [m for m in models if m not in used_models]
            if available:
                assigned_model = available[0]
            else:
                assigned_model = models[model_idx % len(models)]
                model_idx += 1
        used_models.add(assigned_model)
        assignments.append(
            {
                "model": assigned_model,
                "role_id": role_id,
                "role_name": role["name"],
                "mandate": role["mandate"],
                "must_include": role["must_include"],
            }
        )

    reverse_map: Dict[str, List[str]] = {}
    for assignment in assignments:
        reverse_map.setdefault(assignment["model"], []).append(assignment["role_id"])
    warnings = [
        (
            f"Model '{model}' is assigned to multiple roles: "
            + ", ".join(sorted(role_ids))
        )
        for model, role_ids in reverse_map.items()
        if len(role_ids) > 1
    ]

    return assignments, warnings


def validate_required_sections(text: str, required_sections: List[str]) -> Dict[str, Any]:
    """Validate required section labels are present in text."""
    lowered = (text or "").lower()
    missing = [section for section in required_sections if section.lower() not in lowered]
    return {"valid": len(missing) == 0, "missing": missing}


def rubric_coverage_from_text(text: str, rubric_dimensions: List[Dict[str, str]]) -> Dict[str, Any]:
    """Check whether each rubric dimension label appears in ranking text."""
    lowered = (text or "").lower()
    present = {}
    for dim in rubric_dimensions:
        label = dim["label"]
        present[label] = label.lower() in lowered
    return {
        "present": present,
        "all_present": all(present.values()) if present else True,
    }


def _estimate_recommendation_overlap(stage1_results: List[Dict[str, Any]]) -> float:
    """Estimate overlap between Stage 1 responses using average pairwise Jaccard similarity."""
    if len(stage1_results) < 2:
        return 0.0

    def token_set(text: str) -> set:
        tokens = set(re.findall(r"[a-zA-Z]{4,}", (text or "").lower()))
        stop = {
            "this",
            "that",
            "with",
            "from",
            "have",
            "your",
            "what",
            "when",
            "where",
            "which",
            "will",
            "should",
            "would",
            "could",
            "their",
            "there",
            "about",
            "because",
            "these",
        }
        return {t for t in tokens if t not in stop}

    token_sets = [token_set(item.get("response", "")) for item in stage1_results]
    pairs = []
    for i in range(len(token_sets)):
        for j in range(i + 1, len(token_sets)):
            a, b = token_sets[i], token_sets[j]
            union = a | b
            if not union:
                pairs.append(0.0)
            else:
                pairs.append(len(a & b) / len(union))
    return round(sum(pairs) / len(pairs), 3) if pairs else 0.0


def _count_unique_risks(stage3_text: str) -> int:
    """Count likely unique risk bullets in the Stage 3 risks section."""
    text = stage3_text or ""
    match = re.search(r"##\s*Risks(.*?)(##\s*[A-Za-z]|$)", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return 0
    block = match.group(1)
    bullets = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*")):
            bullets.append(stripped.lstrip("-* ").strip().lower())
    return len(set(b for b in bullets if b))


def build_run_diagnostics(
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    stage3_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Build run diagnostics used by guardrail evaluation."""
    role_items = [item for item in stage1_results if "role_validation" in item]
    role_validation_total = sum(
        1 for item in role_items if item.get("role_validation", {}).get("valid")
    )
    role_validation_expected = len(role_items)
    rubric_items = [item for item in stage2_results if "rubric_coverage" in item]
    rubric_all_present = sum(
        1 for item in rubric_items if item.get("rubric_coverage", {}).get("all_present")
    )
    contradiction_flags = sum(
        (item.get("ranking", "").lower().count("contradict"))
        for item in stage2_results
    )
    unique_risk_count = _count_unique_risks(stage3_result.get("response", ""))
    overlap_score = _estimate_recommendation_overlap(stage1_results)
    return {
        "role_schema_compliance": {
            "valid": role_validation_total,
            "total": role_validation_expected,
        },
        "rubric_coverage": {
            "all_present_count": rubric_all_present,
            "total": len(rubric_items),
        },
        "contradiction_flags_count": contradiction_flags,
        "unique_risk_count": unique_risk_count,
        "recommendation_overlap_score": overlap_score,
        "stage3_required_sections_valid": stage3_result.get("section_validation", {}).get("valid"),
    }


def evaluate_guardrails(
    diagnostics: Dict[str, Any],
    *,
    thresholds: Optional[Dict[str, Any]] = None,
    enforcement_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate diagnostics against thresholds and return guardrail status."""
    mode = enforcement_mode or GUARDRAIL_ENFORCEMENT_MODE
    if mode == "off":
        return {"status": "off", "violations": []}

    thresholds = thresholds or GUARDRAIL_THRESHOLDS
    violations: List[str] = []

    role_valid = diagnostics.get("role_schema_compliance", {}).get("valid", 0)
    role_total = diagnostics.get("role_schema_compliance", {}).get("total", 0)
    role_ratio = (role_valid / role_total) if role_total else None
    if role_ratio is not None and role_ratio < thresholds["role_schema_min_ratio"]:
        violations.append(
            f"Role schema compliance ratio {role_ratio:.2f} below "
            f"{thresholds['role_schema_min_ratio']:.2f}"
        )

    rubric_present = diagnostics.get("rubric_coverage", {}).get("all_present_count", 0)
    rubric_total = diagnostics.get("rubric_coverage", {}).get("total", 0)
    rubric_ratio = (rubric_present / rubric_total) if rubric_total else None
    if rubric_ratio is not None and rubric_ratio < thresholds["rubric_coverage_min_ratio"]:
        violations.append(
            f"Rubric coverage ratio {rubric_ratio:.2f} below "
            f"{thresholds['rubric_coverage_min_ratio']:.2f}"
        )

    stage3_sections_valid = diagnostics.get("stage3_required_sections_valid")
    if stage3_sections_valid is False:
        violations.append("Stage 3 required sections missing")

    overlap = diagnostics.get("recommendation_overlap_score", 0.0)
    if overlap > thresholds["max_recommendation_overlap"]:
        violations.append(
            f"Recommendation overlap {overlap:.2f} above "
            f"{thresholds['max_recommendation_overlap']:.2f}"
        )

    unique_risk_count = diagnostics.get("unique_risk_count", 0)
    if unique_risk_count < thresholds["min_unique_risk_count"]:
        violations.append(
            f"Unique risk count {unique_risk_count} below "
            f"{thresholds['min_unique_risk_count']}"
        )

    if not violations:
        return {"status": "pass", "violations": []}
    if mode == "strict_fail":
        return {"status": "fail", "violations": violations}
    return {"status": "degraded", "violations": violations}


def _default_run_context(council_models: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build fallback run context when none is provided."""
    default_profile = get_profile(DEFAULT_PROFILE_ID)
    resolved_models = council_models or COUNCIL_MODELS
    return {
        "profile_id": default_profile["id"],
        "profile": default_profile,
        "packet_id": None,
        "packet_title": None,
        "packet_as_of": None,
        "research_packet": None,
        "role_assignments": assign_perspective_roles(resolved_models, default_profile),
    }


def _simplify_role_assignments(assignments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Project role assignments to a stable, UI-safe metadata shape."""
    return [
        {
            "model": assignment.get("model"),
            "role_id": assignment.get("role_id"),
            "role_name": assignment.get("role_name"),
        }
        for assignment in assignments
    ]


def _run_context_metadata(run_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build metadata-safe run context summary."""
    context = run_context or {}
    return {
        "model_pairing_id": context.get("model_pairing_id"),
        "profile_id": context.get("profile_id"),
        "packet_id": context.get("packet_id"),
        "packet_title": context.get("packet_title"),
        "packet_as_of": context.get("packet_as_of"),
    }


def _build_stage2_metadata(
    run_context: Optional[Dict[str, Any]],
    label_to_model: Dict[str, str],
    aggregate_rankings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build metadata available at Stage 2 completion."""
    context = run_context or {}
    return {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
        "run_context": _run_context_metadata(context),
        "role_assignments": _simplify_role_assignments(context.get("role_assignments", [])),
        "role_assignment_warnings": context.get("role_assignment_warnings", []),
        "model_resolution": context.get("model_resolution", {}),
        "fallback_events": context.get("fallback_events", []),
    }


def _apply_guardrail_policy(
    stage3_result: Dict[str, Any],
    guardrail_status: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply strict-fail guardrail policy to Stage 3 output."""
    if guardrail_status.get("status") != "fail":
        return stage3_result

    violation_lines = "\n".join(f"- {item}" for item in guardrail_status.get("violations", []))
    return {
        "model": stage3_result.get("model") or CHAIRMAN_MODEL,
        "response": (
            "Guardrail enforcement blocked final verdict because required quality gates failed.\n\n"
            "Violations:\n"
            f"{violation_lines}\n\n"
            "Adjust profile/packet inputs or thresholds, then retry."
        ),
        "section_validation": {"valid": False, "missing": []},
    }


def _aggregate_usage(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sum usage fields across a list of result items that may contain 'usage' and 'cost'."""
    prompt = 0
    completion = 0
    total = 0
    cost = 0.0
    has_usage = False
    has_cost = False
    for item in items:
        usage = item.get("usage")
        if isinstance(usage, dict):
            has_usage = True
            prompt += usage.get("prompt_tokens") or 0
            completion += usage.get("completion_tokens") or 0
            total += usage.get("total_tokens") or 0
        if item.get("cost") is not None:
            has_cost = True
            try:
                cost += float(item["cost"])
            except (TypeError, ValueError):
                pass
    result: Dict[str, Any] = {}
    if has_usage:
        result["prompt_tokens"] = prompt
        result["completion_tokens"] = completion
        result["total_tokens"] = total
    if has_cost:
        result["total_cost"] = round(cost, 8)
    return result


def _build_telemetry(
    stage_timings: Dict[str, Dict[str, float]],
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    stage3_result: Dict[str, Any],
    total_start: float,
    total_end: float,
) -> Dict[str, Any]:
    """Assemble the telemetry block for assistant metadata."""
    telemetry: Dict[str, Any] = {
        "total_ms": round((total_end - total_start) * 1000),
    }

    for stage_name, timing in stage_timings.items():
        telemetry[f"{stage_name}_ms"] = round(
            (timing["end"] - timing["start"]) * 1000
        )

    telemetry["stage1_usage"] = _aggregate_usage(stage1_results)
    telemetry["stage2_usage"] = _aggregate_usage(stage2_results)
    telemetry["stage3_usage"] = _aggregate_usage([stage3_result])

    all_items = list(stage1_results) + list(stage2_results) + [stage3_result]
    telemetry["total_usage"] = _aggregate_usage(all_items)

    model_details: List[Dict[str, Any]] = []
    for item in all_items:
        detail: Dict[str, Any] = {"model": item.get("model")}
        if item.get("model_used"):
            detail["model_used"] = item["model_used"]
        if item.get("usage"):
            detail["usage"] = item["usage"]
        if item.get("cost") is not None:
            detail["cost"] = item["cost"]
        model_details.append(detail)
    telemetry["per_model"] = model_details

    return telemetry


def _build_assistant_metadata(
    run_context: Optional[Dict[str, Any]],
    label_to_model: Dict[str, str],
    aggregate_rankings: List[Dict[str, Any]],
    diagnostics: Dict[str, Any],
    guardrail_status: Dict[str, Any],
    telemetry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build final assistant metadata contract."""
    metadata = _build_stage2_metadata(run_context, label_to_model, aggregate_rankings)
    metadata["diagnostics"] = diagnostics
    metadata["guardrail_status"] = guardrail_status
    if telemetry is not None:
        metadata["telemetry"] = telemetry
    return metadata


async def _emit_progress(
    progress_callback: Optional[ProgressCallback],
    event_type: str,
    *,
    data: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> None:
    """Emit a progress event when a callback is provided."""
    if progress_callback is None:
        return

    event: Dict[str, Any] = {"type": event_type}
    if data is not None:
        event["data"] = data
    if metadata is not None:
        event["metadata"] = metadata
    if message is not None:
        event["message"] = message
    await progress_callback(event)


async def stage1_collect_responses(
    user_query: str,
    interrogation: Optional[Dict[str, Any]] = None,
    run_context: Optional[Dict[str, Any]] = None,
    council_models: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models.

    Args:
        user_query: The user's question

    Returns:
        List of dicts with 'model' and 'response' keys
    """
    interrogator_context = format_interrogation_context(interrogation)
    selected_models = council_models or COUNCIL_MODELS
    packet = (run_context or {}).get("research_packet")
    packet_context = format_research_packet_context(packet)
    profile = (run_context or {}).get("profile")

    # Profile-aware path: enforce perspective role cards with model-specific prompts.
    if profile:
        role_assignments = (run_context or {}).get("role_assignments") or assign_perspective_roles(
            selected_models,
            profile,
        )
        if run_context is not None:
            run_context["role_assignments"] = role_assignments

        required_fields = profile.get("required_context_fields", [])
        required_fields_text = ", ".join(required_fields) if required_fields else "(none)"
        stage1_tasks = []
        for assignment in role_assignments:
            must_include = "\n".join(f"- {item}" for item in assignment["must_include"])
            prompt = f"""You are a council member responding from a specific perspective role.

Role Card
- Role: {assignment['role_name']} ({assignment['role_id']})
- Mandate: {assignment['mandate']}

Non-negotiable required sections in your answer (use these labels):
{must_include}
- Where I Disagree

Profile Requirements
- Profile: {profile.get('name', profile.get('id'))}
- Required context fields to address directly where possible: {required_fields_text}

Original Query:
{user_query}

Interrogator Context:
{interrogator_context or "(none)"}

Research Packet:
{packet_context or "(none)"}

Output constraints:
1) Keep your perspective distinct from likely consensus.
2) Explicitly call out assumptions vs facts.
3) Include concrete actions, not only abstract advice.
"""
            stage1_tasks.append(
                (
                    assignment["model"],
                    assignment.get("fallback_models", []),
                    [{"role": "user", "content": prompt}],
                )
            )

        async def _query_with_single_fallback(
            primary_model: str,
            fallback_models: List[str],
            messages: List[Dict[str, str]],
        ) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
            response, err = await query_model_with_error(primary_model, messages)
            if response is not None:
                return primary_model, response, None
            if not fallback_models:
                return primary_model, None, err
            fallback_model = fallback_models[0]
            fb_response, fb_err = await query_model_with_error(fallback_model, messages)
            if run_context is not None:
                run_context.setdefault("fallback_events", []).append(
                    {
                        "slot": "stage1_role",
                        "from_model": primary_model,
                        "to_model": fallback_model,
                        "success": fb_response is not None,
                        "reason": err,
                    }
                )
            if fb_response is not None:
                return fallback_model, fb_response, None
            combined = f"primary_error={err}; fallback_error={fb_err}"
            return primary_model, None, combined

        responses = await asyncio.gather(
            *[
                _query_with_single_fallback(primary, fallbacks, msgs)
                for primary, fallbacks, msgs in stage1_tasks
            ]
        )
        stage1_results: List[Dict[str, Any]] = []
        for assignment, (resolved_model, response, err) in zip(role_assignments, responses):
            if response is None:
                continue
            text = response.get("content") or ""
            validation = validate_required_sections(text, assignment["must_include"] + ["Where I Disagree"])
            item: Dict[str, Any] = {
                "model": resolved_model,
                "perspective_role_id": assignment["role_id"],
                "perspective_role_name": assignment["role_name"],
                "response": text,
                "role_validation": validation,
                "error": err,
            }
            if response.get("usage"):
                item["usage"] = response["usage"]
            if response.get("cost") is not None:
                item["cost"] = response["cost"]
            if response.get("model_used"):
                item["model_used"] = response["model_used"]
            stage1_results.append(item)
        return stage1_results

    # Legacy path: same prompt for all models if no profile context provided.
    if interrogator_context:
        prompt = (
            "You are answering the original user query. Use both the original query and the "
            "clarifying context collected by the Interrogator.\n\n"
            f"Original Query:\n{user_query}\n\n"
            f"{interrogator_context}\n\n"
            "Now provide your best answer to the original query."
        )
    else:
        prompt = user_query

    messages = [{"role": "user", "content": prompt}]
    responses = await query_models_parallel(selected_models, messages)

    stage1_results = []
    for model, response in responses.items():
        if response is not None:
            item: Dict[str, Any] = {"model": model, "response": response.get("content", "")}
            if response.get("usage"):
                item["usage"] = response["usage"]
            if response.get("cost") is not None:
                item["cost"] = response["cost"]
            if response.get("model_used"):
                item["model_used"] = response["model_used"]
            stage1_results.append(item)
    return stage1_results


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    run_context: Optional[Dict[str, Any]] = None,
    council_models: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    selected_models = council_models or COUNCIL_MODELS
    """
    Stage 2: Each model ranks the anonymized responses.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1

    Returns:
        Tuple of (rankings list, label_to_model mapping)
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    profile = (run_context or {}).get("profile")
    rubric_block = ""
    if profile:
        dim_lines = []
        for dim in profile.get("rubric_dimensions", []):
            dim_lines.append(
                f"- {dim['label']}: {dim['description']}"
            )
        rubric_block = (
            "Use the following profile rubric dimensions when evaluating each response. "
            "For each response, include 0-10 scores and brief rationale for EVERY dimension:\n"
            + "\n".join(dim_lines)
            + "\n"
        )

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

{rubric_block}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]

    # Get rankings from all council models in parallel
    responses = await query_models_parallel(selected_models, messages)

    stage2_results = []
    for model, response in responses.items():
        if response is not None:
            full_text = response.get('content', '')
            parsed = parse_ranking_from_text(full_text)
            rubric_coverage = (
                rubric_coverage_from_text(full_text, profile.get("rubric_dimensions", []))
                if profile
                else {"present": {}, "all_present": True}
            )
            item: Dict[str, Any] = {
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed,
                "rubric_coverage": rubric_coverage,
            }
            if response.get("usage"):
                item["usage"] = response["usage"]
            if response.get("cost") is not None:
                item["cost"] = response["cost"]
            if response.get("model_used"):
                item["model_used"] = response["model_used"]
            stage2_results.append(item)

    return stage2_results, label_to_model


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    run_context: Optional[Dict[str, Any]] = None,
    chairman_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2

    Returns:
        Dict with 'model' and 'response' keys
    """
    selected_chairman_model = chairman_model or CHAIRMAN_MODEL
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    profile = (run_context or {}).get("profile")
    packet = (run_context or {}).get("research_packet")
    profile_name = profile.get("name", profile.get("id", "default")) if profile else "default"
    required_sections = (
        profile.get("stage3_required_sections", [])
        if profile
        else ["Facts", "Assumptions", "Reconciliation", "Risks", "Recommendation"]
    )
    required_sections_text = "\n".join(f"- {section}" for section in required_sections)
    packet_context = format_research_packet_context(packet)

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Profile:
{profile_name}

Research Packet:
{packet_context or "(none)"}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

You MUST include these markdown sections with explicit headings:
{required_sections_text}

For each claim, clearly separate validated facts from assumptions when uncertain.
Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

    messages = [{"role": "user", "content": chairman_prompt}]

    response, err = await query_model_with_error(selected_chairman_model, messages)
    if response is None and run_context is not None:
        chairman_fallbacks = (run_context.get("model_resolution", {}) or {}).get(
            "chairman_fallbacks", []
        )
        if chairman_fallbacks:
            fallback_model = chairman_fallbacks[0]
            fb_response, fb_err = await query_model_with_error(fallback_model, messages)
            run_context.setdefault("fallback_events", []).append(
                {
                    "slot": "chairman",
                    "from_model": selected_chairman_model,
                    "to_model": fallback_model,
                    "success": fb_response is not None,
                    "reason": err,
                }
            )
            if fb_response is not None:
                selected_chairman_model = fallback_model
                response, err = fb_response, None
            else:
                err = f"primary_error={err}; fallback_error={fb_err}"

    if response is None:
        err_part = f" ({err})" if err else ""
        extra = (
            " Common causes: invalid CHAIRMAN_MODEL slug (verify at https://openrouter.ai/models ), "
            "insufficient credits, or the chairman prompt exceeding the model context limit."
        )
        return {
            "model": selected_chairman_model,
            "response": f"Error: Unable to generate final synthesis.{err_part}{extra}",
        }

    response_text = response.get("content") or ""
    section_validation = validate_required_sections(response_text, required_sections)
    result: Dict[str, Any] = {
        "model": selected_chairman_model,
        "response": response_text,
        "section_validation": section_validation,
    }
    if response.get("usage"):
        result["usage"] = response["usage"]
    if response.get("cost") is not None:
        result["cost"] = response["cost"]
    if response.get("model_used"):
        result["model_used"] = response["model_used"]
    return result


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    import re

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]

            # Fallback: Extract all "Response X" patterns in order
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    # Fallback: try to find any "Response X" patterns in order
    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']

        # Parse the ranking from the structured format
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message

    Returns:
        A short title (3-5 words)
    """
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use gemini-2.5-flash for title generation (fast and cheap)
    response = await query_model("google/gemini-2.5-flash", messages, timeout=30.0)

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(
    user_query: str,
    interrogation: Optional[Dict[str, Any]] = None,
    run_context: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    council_models: Optional[List[str]] = None,
    chairman_model: Optional[str] = None,
    model_pairing_id: Optional[str] = None,
    role_assignments_override: Optional[Dict[str, str]] = None,
) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete 3-stage council process.

    Args:
        user_query: The user's question

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
    """
    selected_models = council_models or COUNCIL_MODELS
    selected_chairman_model = chairman_model or CHAIRMAN_MODEL
    if run_context is None:
        run_context = _default_run_context(selected_models)

    run_context["model_pairing_id"] = model_pairing_id
    profile = run_context.get("profile")
    if profile:
        role_assignments, warnings = resolve_perspective_roles(
            selected_models,
            profile,
            role_assignments_override,
        )
        fallback_map = ((run_context.get("model_resolution") or {}).get("council_fallbacks") or {})
        if fallback_map:
            for assignment in role_assignments:
                assignment["fallback_models"] = fallback_map.get(assignment["model"], [])
        run_context["role_assignments"] = role_assignments
        run_context["role_assignment_warnings"] = warnings

    total_start = time.perf_counter()
    stage_timings: Dict[str, Dict[str, float]] = {}

    # Stage 1: Collect individual responses
    await _emit_progress(progress_callback, "stage1_start")
    stage_timings["stage1"] = {"start": time.perf_counter()}
    stage1_results = await stage1_collect_responses(
        user_query,
        interrogation=interrogation,
        run_context=run_context,
        council_models=selected_models,
    )
    stage_timings["stage1"]["end"] = time.perf_counter()
    await _emit_progress(progress_callback, "stage1_complete", data=stage1_results)

    # If no models responded successfully, return error
    if not stage1_results:
        stage3_result = {
            "model": "error",
            "response": "All models failed to respond. Please try again."
        }
        await _emit_progress(progress_callback, "stage2_start")
        await _emit_progress(progress_callback, "stage2_complete", data=[], metadata={})
        await _emit_progress(progress_callback, "stage3_start")
        await _emit_progress(progress_callback, "stage3_complete", data=stage3_result, metadata={})
        return [], [], stage3_result, {}

    # Stage 2: Collect rankings
    await _emit_progress(progress_callback, "stage2_start")
    stage_timings["stage2"] = {"start": time.perf_counter()}
    stage2_results, label_to_model = await stage2_collect_rankings(
        user_query,
        stage1_results,
        run_context=run_context,
        council_models=selected_models,
    )
    stage_timings["stage2"]["end"] = time.perf_counter()

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
    stage2_metadata = _build_stage2_metadata(run_context, label_to_model, aggregate_rankings)
    await _emit_progress(
        progress_callback,
        "stage2_complete",
        data=stage2_results,
        metadata=stage2_metadata,
    )

    # Stage 3: Synthesize final answer
    await _emit_progress(progress_callback, "stage3_start")
    stage_timings["stage3"] = {"start": time.perf_counter()}
    stage3_result = await stage3_synthesize_final(
        user_query,
        stage1_results,
        stage2_results,
        run_context=run_context,
        chairman_model=selected_chairman_model,
    )
    stage_timings["stage3"]["end"] = time.perf_counter()
    total_end = time.perf_counter()

    diagnostics = build_run_diagnostics(stage1_results, stage2_results, stage3_result)
    guardrail_status = evaluate_guardrails(diagnostics)
    stage3_result = _apply_guardrail_policy(stage3_result, guardrail_status)
    telemetry = _build_telemetry(
        stage_timings, stage1_results, stage2_results, stage3_result,
        total_start, total_end,
    )
    metadata = _build_assistant_metadata(
        run_context,
        label_to_model,
        aggregate_rankings,
        diagnostics,
        guardrail_status,
        telemetry=telemetry,
    )
    await _emit_progress(
        progress_callback,
        "stage3_complete",
        data=stage3_result,
        metadata=metadata,
    )

    return stage1_results, stage2_results, stage3_result, metadata
