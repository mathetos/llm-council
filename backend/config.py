"""Configuration for the LLM Council."""

import os
from typing import Any, Dict, List
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# HTTP port for uvicorn (override if 8001 is already in use)
def _backend_port() -> int:
    raw = os.getenv("BACKEND_PORT", "8001").strip()
    try:
        p = int(raw)
        return p if 1 <= p <= 65535 else 8001
    except ValueError:
        return 8001


BACKEND_PORT = _backend_port()


def _parse_bounded_int(
    value: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Parse an int and clamp to a bounded range."""
    try:
        parsed = int((value or "").strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def _parse_bounded_float(
    value: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    """Parse a float and clamp to a bounded range."""
    try:
        parsed = float((value or "").strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def _build_council_profiles() -> Dict[str, Dict[str, Any]]:
    """Build guardrail-only profile definitions (no profile-specific model swaps)."""
    return {
        "marketing": {
            "id": "marketing",
            "name": "Marketing Council",
            "description": "Positioning, messaging, channel strategy, and conversion-oriented plans.",
            "required_context_fields": [
                "target_audience",
                "goal",
                "offer_or_value_prop",
                "distribution_channel",
                "constraints",
            ],
            "rubric_dimensions": [
                {
                    "id": "strategic_clarity",
                    "label": "Strategic Clarity",
                    "description": "Clear objective, audience, and path to impact.",
                },
                {
                    "id": "message_resonance",
                    "label": "Message Resonance",
                    "description": "Likelihood message will land with target audience.",
                },
                {
                    "id": "differentiation",
                    "label": "Differentiation Strength",
                    "description": "How clearly this stands apart from alternatives.",
                },
                {
                    "id": "testability",
                    "label": "Testability",
                    "description": "Quality of hypotheses and measurable experiments.",
                },
                {
                    "id": "execution_feasibility",
                    "label": "Execution Feasibility",
                    "description": "Practicality within constraints and timeline.",
                },
            ],
            "perspective_roles": [
                {
                    "id": "systems_thinker",
                    "name": "Systems Thinker",
                    "mandate": "Map how channel, message, offer, and funnel stage interact.",
                    "must_include": ["Dependencies", "Second-Order Effects", "Failure Condition"],
                },
                {
                    "id": "conversion_operator",
                    "name": "Conversion Operator",
                    "mandate": "Prioritize practical experiments and execution sequence.",
                    "must_include": ["Execution Plan", "Experiment Design", "Resource Assumptions"],
                },
                {
                    "id": "audience_psychologist",
                    "name": "Audience Psychologist",
                    "mandate": "Interrogate user motivations, objections, and trust barriers.",
                    "must_include": ["Audience Insight", "Objections", "Trust Risks"],
                },
                {
                    "id": "skeptic_auditor",
                    "name": "Skeptic Auditor",
                    "mandate": "Stress-test overclaims, weak evidence, and downside risk.",
                    "must_include": ["Evidence Gaps", "Risk Register", "Where I Disagree"],
                },
            ],
            "stage3_required_sections": [
                "Facts",
                "Assumptions",
                "Reconciliation",
                "Risks",
                "Recommendation",
            ],
        },
        "product_development": {
            "id": "product_development",
            "name": "Product Development Council",
            "description": "Product strategy, scope, feasibility, sequencing, and adoption risk.",
            "required_context_fields": [
                "user_problem",
                "success_metric",
                "scope_constraints",
                "timeline",
                "technical_constraints",
            ],
            "rubric_dimensions": [
                {
                    "id": "problem_solution_fit",
                    "label": "Problem-Solution Fit",
                    "description": "How directly proposal addresses user problem.",
                },
                {
                    "id": "implementation_realism",
                    "label": "Implementation Realism",
                    "description": "Technical feasibility with available resources.",
                },
                {
                    "id": "risk_coverage",
                    "label": "Risk Coverage",
                    "description": "Depth of identified product and delivery risks.",
                },
                {
                    "id": "dependency_management",
                    "label": "Dependency Management",
                    "description": "Awareness of sequencing and cross-team dependencies.",
                },
                {
                    "id": "measurement_quality",
                    "label": "Measurement Quality",
                    "description": "Clarity of success metrics and validation loops.",
                },
            ],
            "perspective_roles": [
                {
                    "id": "pm_strategist",
                    "name": "PM Strategist",
                    "mandate": "Maximize user value under business constraints.",
                    "must_include": ["User Value Thesis", "Scope Boundaries", "Tradeoffs"],
                },
                {
                    "id": "staff_engineer",
                    "name": "Staff Engineer",
                    "mandate": "Ground plan in architecture and implementation realities.",
                    "must_include": ["Architecture Notes", "Technical Risks", "Dependency Graph"],
                },
                {
                    "id": "adoption_analyst",
                    "name": "Adoption Analyst",
                    "mandate": "Model behavior change and rollout adoption risk.",
                    "must_include": ["Adoption Risks", "Rollout Plan", "Instrumentation"],
                },
                {
                    "id": "failure_mode_reviewer",
                    "name": "Failure Mode Reviewer",
                    "mandate": "Surface edge cases, rollback paths, and irreversible downsides.",
                    "must_include": ["Failure Modes", "Rollback Plan", "Where I Disagree"],
                },
            ],
            "stage3_required_sections": [
                "Facts",
                "Assumptions",
                "Reconciliation",
                "Risks",
                "Recommendation",
            ],
        },
        "business_development": {
            "id": "business_development",
            "name": "Business Development Council",
            "description": "Partnerships, deals, outreach strategy, and commercial execution.",
            "required_context_fields": [
                "target_segment_or_account",
                "commercial_goal",
                "value_exchange",
                "timeline",
                "constraints",
            ],
            "rubric_dimensions": [
                {
                    "id": "deal_plausibility",
                    "label": "Deal Plausibility",
                    "description": "Likelihood that plan can realistically close.",
                },
                {
                    "id": "stakeholder_strategy",
                    "label": "Stakeholder Strategy",
                    "description": "Quality of buying-committee and influence mapping.",
                },
                {
                    "id": "objection_readiness",
                    "label": "Objection Readiness",
                    "description": "Preparedness for major counterarguments and blockers.",
                },
                {
                    "id": "commercial_quality",
                    "label": "Commercial Quality",
                    "description": "Strength of economics and strategic upside.",
                },
                {
                    "id": "next_step_specificity",
                    "label": "Next-Step Specificity",
                    "description": "Concrete and executable immediate actions.",
                },
            ],
            "perspective_roles": [
                {
                    "id": "market_mapper",
                    "name": "Market Mapper",
                    "mandate": "Analyze account/segment fit and strategic landscape.",
                    "must_include": ["Fit Analysis", "Strategic Position", "Assumptions"],
                },
                {
                    "id": "deal_operator",
                    "name": "Deal Operator",
                    "mandate": "Translate strategy into concrete outreach and progression steps.",
                    "must_include": ["Sequence Plan", "Milestones", "Decision Path"],
                },
                {
                    "id": "objection_strategist",
                    "name": "Objection Strategist",
                    "mandate": "Pre-handle objections and negotiation friction.",
                    "must_include": ["Top Objections", "Response Strategy", "Fallbacks"],
                },
                {
                    "id": "commercial_risk_auditor",
                    "name": "Commercial Risk Auditor",
                    "mandate": "Pressure-test downside and unfavorable deal structures.",
                    "must_include": ["Commercial Risks", "Guardrails", "Where I Disagree"],
                },
            ],
            "stage3_required_sections": [
                "Facts",
                "Assumptions",
                "Reconciliation",
                "Risks",
                "Recommendation",
            ],
        },
    }


def _validate_profiles(profiles: Dict[str, Dict[str, Any]]) -> None:
    """Fail fast on invalid profile contracts."""
    if not profiles:
        raise ValueError("COUNCIL_PROFILES cannot be empty")

    required_profile_keys = {
        "id",
        "name",
        "description",
        "required_context_fields",
        "rubric_dimensions",
        "perspective_roles",
        "stage3_required_sections",
    }
    for profile_id, profile in profiles.items():
        missing = required_profile_keys - set(profile.keys())
        if missing:
            raise ValueError(f"Profile '{profile_id}' missing keys: {sorted(missing)}")
        if profile["id"] != profile_id:
            raise ValueError(f"Profile '{profile_id}' has mismatched id '{profile['id']}'")
        if not profile["required_context_fields"]:
            raise ValueError(f"Profile '{profile_id}' required_context_fields cannot be empty")
        if not profile["rubric_dimensions"]:
            raise ValueError(f"Profile '{profile_id}' rubric_dimensions cannot be empty")
        if not profile["perspective_roles"]:
            raise ValueError(f"Profile '{profile_id}' perspective_roles cannot be empty")
        if not profile["stage3_required_sections"]:
            raise ValueError(f"Profile '{profile_id}' stage3_required_sections cannot be empty")

        rubric_ids = set()
        for dim in profile["rubric_dimensions"]:
            if not {"id", "label", "description"} <= set(dim.keys()):
                raise ValueError(f"Profile '{profile_id}' has invalid rubric dimension: {dim}")
            if dim["id"] in rubric_ids:
                raise ValueError(f"Profile '{profile_id}' has duplicate rubric id '{dim['id']}'")
            rubric_ids.add(dim["id"])

        role_ids = set()
        for role in profile["perspective_roles"]:
            if not {"id", "name", "mandate", "must_include"} <= set(role.keys()):
                raise ValueError(f"Profile '{profile_id}' has invalid role card: {role}")
            if role["id"] in role_ids:
                raise ValueError(f"Profile '{profile_id}' has duplicate role id '{role['id']}'")
            if not role["must_include"]:
                raise ValueError(
                    f"Profile '{profile_id}' role '{role['id']}' must_include cannot be empty"
                )
            role_ids.add(role["id"])

# Council members — OpenRouter model ids (must match https://openrouter.ai/models exactly).
COUNCIL_MODELS = [
    "google/gemini-3.1-flash-lite-preview",
    "anthropic/claude-sonnet-4.6",
    "openai/gpt-4o-mini",
]

# Chairman — synthesizes Stage 3. Use any valid OpenRouter id (same as council or a stronger model).
# Default matches the title helper slug in council.py so a missing/renamed preview id does not break Stage 3 alone.
CHAIRMAN_MODEL = "google/gemini-2.5-flash"

# Runtime-selectable model pairings surfaced in the Settings modal.
MODEL_PAIRINGS: Dict[str, Dict[str, Any]] = {
    "premium": {
        "id": "premium",
        "label": "Premium",
        "description": "Best overall quality with paid frontier models.",
        "council_models": COUNCIL_MODELS,
        "chairman_model": CHAIRMAN_MODEL,
        "interrogator_model": CHAIRMAN_MODEL,
    },
    "free_auto_router": {
        "id": "free_auto_router",
        "label": "Free (Auto Router)",
        "description": "Use OpenRouter free router with diverse free backups.",
        "council_models": [
            "openrouter/free",
            "google/gemma-3-27b-it:free",
            "nvidia/nemotron-3-nano-30b-a3b:free",
        ],
        "chairman_model": "openrouter/free",
        "interrogator_model": "openrouter/free",
    },
}
DEFAULT_MODEL_PAIRING_ID = "premium"

COUNCIL_PROFILES = _build_council_profiles()
_validate_profiles(COUNCIL_PROFILES)

DEFAULT_PROFILE_ID = (os.getenv("DEFAULT_PROFILE_ID", "marketing") or "marketing").strip()
if DEFAULT_PROFILE_ID not in COUNCIL_PROFILES:
    print(
        f"Invalid DEFAULT_PROFILE_ID='{DEFAULT_PROFILE_ID}'. "
        "Falling back to 'marketing'."
    )
    DEFAULT_PROFILE_ID = "marketing"

GUARDRAIL_ENFORCEMENT_MODE = (
    os.getenv("GUARDRAIL_ENFORCEMENT_MODE", "degraded") or "degraded"
).strip().lower()
if GUARDRAIL_ENFORCEMENT_MODE not in {"off", "degraded", "strict_fail"}:
    print(
        f"Invalid GUARDRAIL_ENFORCEMENT_MODE='{GUARDRAIL_ENFORCEMENT_MODE}'. "
        "Falling back to 'degraded'."
    )
    GUARDRAIL_ENFORCEMENT_MODE = "degraded"

GUARDRAIL_THRESHOLDS = {
    "role_schema_min_ratio": _parse_bounded_float(
        os.getenv("GUARDRAIL_ROLE_SCHEMA_MIN_RATIO", "1.0"),
        default=1.0,
        minimum=0.0,
        maximum=1.0,
    ),
    "rubric_coverage_min_ratio": _parse_bounded_float(
        os.getenv("GUARDRAIL_RUBRIC_COVERAGE_MIN_RATIO", "1.0"),
        default=1.0,
        minimum=0.0,
        maximum=1.0,
    ),
    "max_recommendation_overlap": _parse_bounded_float(
        os.getenv("GUARDRAIL_MAX_RECOMMENDATION_OVERLAP", "0.80"),
        default=0.80,
        minimum=0.0,
        maximum=1.0,
    ),
    "min_unique_risk_count": _parse_bounded_int(
        os.getenv("GUARDRAIL_MIN_UNIQUE_RISK_COUNT", "1"),
        default=1,
        minimum=0,
        maximum=50,
    ),
}

# Interrogator — asks bounded clarification questions before the first council run.
# Defaults to chairman model unless explicitly overridden.
INTERROGATOR_MODEL = (os.getenv("INTERROGATOR_MODEL") or CHAIRMAN_MODEL).strip() or CHAIRMAN_MODEL
MODEL_PAIRINGS["premium"]["interrogator_model"] = INTERROGATOR_MODEL

_raw_min = _parse_bounded_int(
    os.getenv("INTERROGATOR_MIN_QUESTIONS", "2"),
    default=2,
    minimum=1,
    maximum=10,
)
_raw_max = _parse_bounded_int(
    os.getenv("INTERROGATOR_MAX_QUESTIONS", "5"),
    default=5,
    minimum=1,
    maximum=10,
)

if _raw_min > _raw_max:
    print(
        "Invalid interrogator bounds (min > max). "
        "Falling back to defaults INTERROGATOR_MIN_QUESTIONS=2 and INTERROGATOR_MAX_QUESTIONS=5."
    )
    INTERROGATOR_MIN_QUESTIONS = 2
    INTERROGATOR_MAX_QUESTIONS = 5
else:
    INTERROGATOR_MIN_QUESTIONS = _raw_min
    INTERROGATOR_MAX_QUESTIONS = _raw_max

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"

# Local research packet store used by profile guardrails.
RESEARCH_PACKETS_DIR = "data/research_packets"


def list_profiles() -> List[Dict[str, str]]:
    """Return minimal profile metadata for UI selectors."""
    return [
        {
            "id": profile["id"],
            "name": profile["name"],
            "description": profile["description"],
        }
        for profile in COUNCIL_PROFILES.values()
    ]


def get_profile(profile_id: str) -> Dict[str, Any]:
    """Resolve a profile by id or raise ValueError."""
    if profile_id not in COUNCIL_PROFILES:
        raise ValueError(f"Unknown profile_id '{profile_id}'")
    return COUNCIL_PROFILES[profile_id]


def list_model_pairings() -> List[Dict[str, str]]:
    """Return model pairing metadata for Settings UI selectors."""
    return [
        {
            "id": pairing["id"],
            "label": pairing["label"],
            "description": pairing["description"],
        }
        for pairing in MODEL_PAIRINGS.values()
    ]


def get_model_pairing(pairing_id: str) -> Dict[str, Any]:
    """Resolve model pairing by id or raise ValueError."""
    if pairing_id not in MODEL_PAIRINGS:
        raise ValueError(f"Unknown model_pairing_id '{pairing_id}'")
    return MODEL_PAIRINGS[pairing_id]


def resolve_model_pairing(pairing_id: str | None) -> Dict[str, Any]:
    """Resolve selected pairing or fall back to default pairing."""
    resolved_id = (pairing_id or DEFAULT_MODEL_PAIRING_ID).strip() or DEFAULT_MODEL_PAIRING_ID
    return get_model_pairing(resolved_id)
