"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
import uuid
import json
import asyncio
import time
import httpx

from . import storage
from .config import (
    BACKEND_PORT,
    DEFAULT_PROFILE_ID,
    DEFAULT_MODEL_PAIRING_ID,
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    INTERROGATOR_MIN_QUESTIONS,
    INTERROGATOR_MAX_QUESTIONS,
    COUNCIL_PROFILES,
    get_profile,
    list_profiles,
    list_model_pairings,
    resolve_model_pairing,
)
from .council import (
    run_full_council,
    generate_conversation_title,
    generate_interrogator_question,
    should_continue_interrogation,
    summarize_interrogation,
    assess_interrogation_coverage,
    is_defer_answer,
    resolve_perspective_roles,
)
from .openrouter import (
    query_model_with_error,
    list_user_visible_models_with_error,
    list_models_with_error,
)

app = FastAPI(title="LLM Council API")

# In-memory sessions for Stage 0 interrogation.
# Keyed by session_id and intentionally ephemeral (server restart clears sessions).
INTERROGATION_SESSIONS: Dict[str, Dict[str, Any]] = {}
PRIVACY_SAFE_MODELS_CACHE: Dict[str, Any] = {
    "expires_at": 0.0,
    "payload": None,
}


def _hydrate_run_context(raw: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Ensure run_context contains full profile and packet objects."""
    if not raw:
        return None

    profile_id = raw.get("profile_id") or DEFAULT_PROFILE_ID
    profile = get_profile(profile_id)
    packet_id = raw.get("packet_id")
    packet = storage.load_research_packet(profile_id, packet_id)

    return {
        "profile_id": profile_id,
        "profile": profile,
        "packet_id": packet.get("packet_id"),
        "packet_title": packet.get("title"),
        "packet_as_of": packet.get("as_of"),
        "research_packet": packet,
        "role_assignments": raw.get("role_assignments", []),
    }


def _resolve_message_context(
    conversation: Dict[str, Any],
    request: "SendMessageRequest",
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Resolve first-message interrogation requirements and hydrated run context.

    Returns:
        (is_first_message, interrogation_or_none, hydrated_run_context_or_none)
    """
    is_first_message = len(conversation.get("messages", [])) == 0
    interrogation = request.interrogation if is_first_message else None
    raw_run_context = (
        request.rerun_context_override
        or ((interrogation or {}).get("run_context") if interrogation else None)
    )

    if is_first_message and not interrogation:
        raise HTTPException(
            status_code=400,
            detail=(
                "Interrogation is required for the first message. "
                "Use /api/conversations/{id}/interrogation/start and /interrogation/answer first."
            ),
        )
    if is_first_message and not raw_run_context:
        raise HTTPException(
            status_code=400,
            detail="Interrogation payload is missing run_context (profile + research packet).",
        )

    if not is_first_message:
        # Reuse latest run context from prior assistant message metadata if available.
        for msg in reversed(conversation.get("messages", [])):
            if msg.get("role") == "assistant" and msg.get("metadata", {}).get("run_context"):
                raw_run_context = msg["metadata"]["run_context"]
                break

    try:
        run_context = _hydrate_run_context(raw_run_context) if raw_run_context else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return is_first_message, interrogation, run_context


def _resolve_pairing_or_400(pairing_id: Optional[str]) -> Dict[str, Any]:
    """Resolve a model pairing id to config or raise HTTP 400."""
    try:
        return resolve_model_pairing(pairing_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _diagnose_openrouter_failure(error_text: str) -> Dict[str, str]:
    """Map raw OpenRouter failure details to actionable user hints."""
    lowered = (error_text or "").lower()
    if "missing or empty" in lowered or "401" in lowered or "403" in lowered:
        return {
            "error_type": "auth",
            "hint": (
                "OpenRouter API key is missing/invalid. "
                "Set OPENROUTER_API_KEY in .env and verify it in OpenRouter."
            ),
        }
    if "402" in lowered or "insufficient" in lowered or "credit" in lowered:
        return {
            "error_type": "credits",
            "hint": "Billing/credits issue. Top up credits or switch to a free pairing.",
        }
    if "404" in lowered or "no allowed providers" in lowered:
        return {
            "error_type": "model_unavailable",
            "hint": "Model/provider is unavailable for your account. Adjust pairing selection.",
        }
    if "429" in lowered or "rate limit" in lowered:
        return {
            "error_type": "rate_limited",
            "hint": "Rate limit hit. Wait briefly and retry testing.",
        }
    if "network error" in lowered or "timeout" in lowered:
        return {
            "error_type": "network",
            "hint": "Network/provider timeout. Retry in 30-60 seconds.",
        }
    if "500" in lowered or "502" in lowered or "503" in lowered:
        return {
            "error_type": "provider",
            "hint": "OpenRouter/provider transient failure. Retry shortly.",
        }
    return {
        "error_type": "unknown",
        "hint": "Unexpected OpenRouter error. Review raw error details.",
    }


def _validate_role_assignment_override(
    run_context: Optional[Dict[str, Any]],
    council_models: List[str],
    role_assignments_override: Optional[Dict[str, str]],
) -> None:
    """Fail fast on invalid role assignment overrides."""
    if not role_assignments_override:
        return
    profile = (run_context or {}).get("profile")
    if not profile:
        return
    resolve_perspective_roles(council_models, profile, role_assignments_override)


async def _apply_free_auto_router_override_or_400(
    pairing: Dict[str, Any],
    free_backup_models_override: Optional[List[str]],
) -> Dict[str, Any]:
    """Apply optional backup-model override for free_auto_router pairing."""
    overrides = [item.strip() for item in (free_backup_models_override or []) if item and item.strip()]
    if not overrides:
        return pairing
    if pairing["id"] != "free_auto_router":
        raise HTTPException(
            status_code=400,
            detail="free_backup_models_override is only supported for free_auto_router pairing",
        )
    if len(overrides) != 2:
        raise HTTPException(
            status_code=400,
            detail="free_backup_models_override must contain exactly 2 models",
        )

    visible_models, err = await list_user_visible_models_with_error()
    if visible_models is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to validate free backup models from /models/user: {err}",
        )

    visible_free = {model for model in visible_models if model.endswith(":free")}
    invalid = sorted(set(overrides) - visible_free)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=(
                "free_backup_models_override contains models not currently eligible for this key: "
                + ", ".join(invalid)
            ),
        )

    deduped: List[str] = []
    for model in overrides:
        if model not in deduped and model != "openrouter/free":
            deduped.append(model)
    if len(deduped) != 2:
        raise HTTPException(
            status_code=400,
            detail="free_backup_models_override must contain two distinct non-router models",
        )

    updated = dict(pairing)
    updated["council_models"] = ["openrouter/free", deduped[0], deduped[1]]
    return updated


def _model_score(model_id: str, metadata: Optional[Dict[str, Any]]) -> float:
    """Score candidate models for deterministic substitution ranking."""
    meta = metadata or {}
    context = float(meta.get("context_length") or 0)
    supported = meta.get("supported_parameters") or []
    tools_support = 1.0 if "tools" in supported else 0.0
    return (context / 1_000_000.0) + (tools_support * 0.25)


def _safe_price_number(value: Any) -> Optional[float]:
    """Parse a pricing field as float; return None on non-numeric values."""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _is_strict_zero_cost_free_model(model: Dict[str, Any]) -> bool:
    """
    Return True for explicit :free variants with non-positive pricing fields.

    This mirrors the spirit of models-page filtering like pricing=free&max_price=0,
    while keeping selection scoped to concrete free variants (not routers).
    """
    model_id = (model.get("id") or "").strip()
    if not model_id.endswith(":free"):
        return False
    if model_id == "openrouter/free":
        return False
    pricing = model.get("pricing") or {}
    if not isinstance(pricing, dict):
        return False
    numeric_prices = [
        _safe_price_number(v)
        for v in pricing.values()
    ]
    numeric_prices = [v for v in numeric_prices if v is not None]
    return bool(numeric_prices) and max(numeric_prices) <= 0.0


def _normalize_free_variant_model_id(model_id: str) -> str:
    """Normalize a model id into its explicit :free variant form."""
    normalized = (model_id or "").strip()
    if not normalized:
        raise ValueError("model_id cannot be empty")
    if normalized.endswith(":free"):
        return normalized
    return f"{normalized}:free"


def _choose_candidate(
    requested_model: str,
    candidates: List[str],
    models_by_id: Dict[str, Dict[str, Any]],
    *,
    used_models: Optional[set] = None,
) -> Optional[str]:
    """Choose best deterministic candidate with family and capability preference."""
    if not candidates:
        return None
    used_models = used_models or set()
    provider_prefix = requested_model.split("/", 1)[0] if "/" in requested_model else ""
    same_family = [m for m in candidates if m.split("/", 1)[0] == provider_prefix and m not in used_models]
    pool = same_family if same_family else [m for m in candidates if m not in used_models]
    if not pool:
        pool = candidates
    ranked = sorted(
        pool,
        key=lambda m: (_model_score(m, models_by_id.get(m)), m),
        reverse=True,
    )
    return ranked[0] if ranked else None


async def _resolve_runtime_pairing(
    pairing: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Resolve runtime models based on /models/user eligibility and /models capabilities.

    Returns a structure with resolved models and transparent substitution traces.
    """
    visible_models, visible_err = await list_user_visible_models_with_error()
    all_models, all_models_err = await list_models_with_error()
    if visible_models is None:
        council_requested = list(pairing["council_models"])
        chairman_requested = pairing["chairman_model"]
        interrogator_requested = pairing["interrogator_model"]
        return {
            "pairing_id": pairing["id"],
            "requested": {
                "council_models": council_requested,
                "chairman_model": chairman_requested,
                "interrogator_model": interrogator_requested,
            },
            "resolved": {
                "council_models": council_requested,
                "chairman_model": chairman_requested,
                "interrogator_model": interrogator_requested,
            },
            "council_fallbacks": {m: [] for m in council_requested},
            "chairman_fallbacks": [],
            "interrogator_fallbacks": [],
            "substitutions": [],
            "eligibility_error": visible_err,
            "catalog_error": all_models_err,
        }
    visible_set = set(visible_models or [])
    models_by_id = {m.get("id"): m for m in (all_models or []) if m.get("id")}

    council_requested = list(pairing["council_models"])
    free_candidates = sorted([m for m in visible_set if m.endswith(":free")])
    paid_candidates = sorted([m for m in visible_set if not m.endswith(":free")])

    substitutions: List[Dict[str, Any]] = []
    used: set = set()
    resolved_council: List[str] = []
    council_fallbacks: Dict[str, List[str]] = {}

    for requested in council_requested:
        if requested in visible_set and requested not in used:
            resolved = requested
        else:
            pool = free_candidates if requested.endswith(":free") or requested == "openrouter/free" else paid_candidates
            resolved = _choose_candidate(requested, pool, models_by_id, used_models=used)
            if resolved is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"No eligible replacement found for council model '{requested}'",
                )
            substitutions.append(
                {
                    "slot": "council",
                    "from_model": requested,
                    "to_model": resolved,
                    "reason": "filtered_or_unavailable",
                }
            )
        used.add(resolved)
        resolved_council.append(resolved)

        fallback_pool = [
            m for m in (free_candidates if resolved.endswith(":free") else paid_candidates)
            if m != resolved
        ]
        fallback = _choose_candidate(resolved, fallback_pool, models_by_id)
        council_fallbacks[resolved] = [fallback] if fallback else []

    chairman_requested = pairing["chairman_model"]
    chairman_pool = free_candidates if chairman_requested.endswith(":free") or chairman_requested == "openrouter/free" else paid_candidates
    resolved_chairman = (
        chairman_requested
        if chairman_requested in visible_set
        else _choose_candidate(chairman_requested, chairman_pool, models_by_id)
    )
    if resolved_chairman is None:
        raise HTTPException(status_code=400, detail=f"No eligible chairman model for '{chairman_requested}'")
    if resolved_chairman != chairman_requested:
        substitutions.append(
            {
                "slot": "chairman",
                "from_model": chairman_requested,
                "to_model": resolved_chairman,
                "reason": "filtered_or_unavailable",
            }
        )
    chairman_fallback = _choose_candidate(
        resolved_chairman,
        [m for m in chairman_pool if m != resolved_chairman],
        models_by_id,
    )

    interrogator_requested = pairing["interrogator_model"]
    interrogator_pool = free_candidates if interrogator_requested.endswith(":free") or interrogator_requested == "openrouter/free" else paid_candidates
    resolved_interrogator = (
        interrogator_requested
        if interrogator_requested in visible_set
        else _choose_candidate(interrogator_requested, interrogator_pool, models_by_id)
    )
    if resolved_interrogator is None:
        raise HTTPException(
            status_code=400,
            detail=f"No eligible interrogator model for '{interrogator_requested}'",
        )
    if resolved_interrogator != interrogator_requested:
        substitutions.append(
            {
                "slot": "interrogator",
                "from_model": interrogator_requested,
                "to_model": resolved_interrogator,
                "reason": "filtered_or_unavailable",
            }
        )
    interrogator_fallback = _choose_candidate(
        resolved_interrogator,
        [m for m in interrogator_pool if m != resolved_interrogator],
        models_by_id,
    )

    return {
        "pairing_id": pairing["id"],
        "requested": {
            "council_models": council_requested,
            "chairman_model": chairman_requested,
            "interrogator_model": interrogator_requested,
        },
        "resolved": {
            "council_models": resolved_council,
            "chairman_model": resolved_chairman,
            "interrogator_model": resolved_interrogator,
        },
        "council_fallbacks": council_fallbacks,
        "chairman_fallbacks": [chairman_fallback] if chairman_fallback else [],
        "interrogator_fallbacks": [interrogator_fallback] if interrogator_fallback else [],
        "substitutions": substitutions,
        "eligibility_error": visible_err,
        "catalog_error": all_models_err,
    }


async def _build_pairing_eligibility(
    pairing: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Build model eligibility statuses from /models/user visibility."""
    pairing_models = list(dict.fromkeys(
        list(pairing["council_models"]) + [pairing["chairman_model"], pairing["interrogator_model"]]
    ))
    visible_models, err = await list_user_visible_models_with_error()
    if visible_models is None:
        checks = [{"model": model, "eligible": None} for model in pairing_models]
        return checks, err

    visible_set = set(visible_models)
    checks = []
    for model in pairing_models:
        eligible = model in visible_set
        checks.append(
            {
                "model": model,
                "eligible": eligible,
                "status": "eligible" if eligible else "filtered",
                "note": (
                    "Visible in /models/user for this API key"
                    if eligible
                    else "Filtered by account/provider preferences before request-time routing"
                ),
            }
        )
    return checks, None


def _merge_council_models_with_role_override(
    base_models: List[str],
    profile: Optional[Dict[str, Any]],
    role_assignments_override: Optional[Dict[str, str]],
) -> List[str]:
    """
    Resolve council models from role overrides in role-card order.

    When explicit role assignments are provided, treat them as the intended run set
    instead of appending base pairing models. Appending can unintentionally balloon
    Stage 2 reviewer count and latency (e.g., 4 role models + 3 base models = 7).
    """
    if not role_assignments_override:
        return base_models
    role_cards = (profile or {}).get("perspective_roles") or []
    ordered_override_models: List[str] = []
    for role in role_cards:
        role_id = role.get("id")
        model = role_assignments_override.get(role_id)
        if model and model not in ordered_override_models:
            ordered_override_models.append(model)

    if not ordered_override_models:
        return base_models

    return ordered_override_models


async def _probe_zdr_compatibility(model_id: str, timeout: float = 12.0) -> Tuple[bool, Optional[str]]:
    """Probe one model with strict privacy policy flags."""
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.strip():
        return False, "OPENROUTER_API_KEY is missing or empty in .env"

    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply exactly: OK"}],
        "max_tokens": 8,
        "temperature": 0,
        "provider": {
            "data_collection": "deny",
            "zdr": True,
        },
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)
            if response.status_code >= 400:
                detail = (response.text or "").replace("\n", " ").strip()
                return False, f"HTTP {response.status_code}: {detail[:320]}"
            return True, None
    except httpx.RequestError as e:
        return False, f"Network error: {e}"


async def _build_privacy_safe_models_payload() -> Dict[str, Any]:
    """Build list of privacy-safe models: visible paid + ZDR-passing free."""
    visible_models, visibility_err = await list_user_visible_models_with_error()
    all_models, catalog_err = await list_models_with_error()
    if visible_models is None:
        return {"models": [], "error": visibility_err, "catalog_error": catalog_err}
    if all_models is None:
        return {"models": [], "error": None, "catalog_error": catalog_err}

    by_id = {item.get("id"): item for item in all_models if item.get("id")}
    visible_set = set(visible_models)
    paid_ids = sorted(
        [
            model_id
            for model_id in visible_set
            if model_id != "openrouter/free" and not model_id.endswith(":free")
        ]
    )
    strict_free_ids = sorted(
        [
            model_id
            for model_id in visible_set
            if _is_strict_zero_cost_free_model(by_id.get(model_id) or {})
        ]
    )

    semaphore = asyncio.Semaphore(6)

    async def _probe_with_limit(model_id: str) -> Tuple[str, bool, Optional[str]]:
        async with semaphore:
            passed, err = await _probe_zdr_compatibility(model_id)
            return model_id, passed, err

    free_probe_results = await asyncio.gather(*[_probe_with_limit(model_id) for model_id in strict_free_ids])
    free_pass_ids = sorted([model_id for model_id, passed, _ in free_probe_results if passed])
    free_failures = [
        {"id": model_id, "error": err}
        for model_id, passed, err in free_probe_results
        if not passed
    ]

    models: List[Dict[str, Any]] = []
    for model_id in paid_ids:
        meta = by_id.get(model_id) or {}
        supported = meta.get("supported_parameters") or []
        models.append(
            {
                "id": model_id,
                "tier": "paid",
                "family": model_id.split("/", 1)[0] if "/" in model_id else model_id,
                "context_length": meta.get("context_length"),
                "supports_tools": "tools" in supported,
            }
        )
    for model_id in free_pass_ids:
        meta = by_id.get(model_id) or {}
        supported = meta.get("supported_parameters") or []
        models.append(
            {
                "id": model_id,
                "tier": "free",
                "family": model_id.split("/", 1)[0] if "/" in model_id else model_id,
                "context_length": meta.get("context_length"),
                "supports_tools": "tools" in supported,
            }
        )

    return {
        "models": models,
        "error": None,
        "catalog_error": catalog_err,
        "counts": {
            "visible_paid": len(paid_ids),
            "visible_strict_free": len(strict_free_ids),
            "privacy_safe_free": len(free_pass_ids),
        },
        "free_probe_failures": free_failures,
        "generated_at_ms": int(time.time() * 1000),
    }

# CORS: fixed dev URLs plus any localhost / 127.0.0.1 port (Vite may use 5174+ if 5173 is taken)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    interrogation: Optional[Dict[str, Any]] = None
    model_pairing_id: Optional[str] = None
    role_assignments_override: Optional[Dict[str, str]] = None
    free_backup_models_override: Optional[List[str]] = None
    rerun_context_override: Optional[Dict[str, Any]] = None


class StartInterrogationRequest(BaseModel):
    """Request to begin Stage 0 interrogation."""
    content: str
    profile_id: Optional[str] = None
    packet_id: Optional[str] = None
    model_pairing_id: Optional[str] = None
    free_backup_models_override: Optional[List[str]] = None


class AnswerInterrogationRequest(BaseModel):
    """Request with a user's answer to an interrogator question."""
    session_id: str
    answer: str


class ConfirmInterrogationRequest(BaseModel):
    """Request to confirm or reject the interrogation summary and proceed."""
    session_id: str
    confirmed: bool


class TestPairingRequest(BaseModel):
    """Request to probe all models in a selected pairing."""
    model_pairing_id: Optional[str] = None
    free_backup_models_override: Optional[List[str]] = None


class FreeVariantCheckRequest(BaseModel):
    """Request to evaluate one model slug against :free availability and eligibility."""
    model_id: str


class SaveVerdictRequest(BaseModel):
    """Request to save a Stage 3 verdict as markdown."""
    assistant_message_index: int


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/profiles")
async def get_profiles():
    """List available guardrail profiles for the council."""
    return {
        "default_profile_id": DEFAULT_PROFILE_ID,
        "profiles": list_profiles(),
    }


@app.get("/api/settings/model-pairings")
async def get_model_pairing_settings():
    """List available model pairings and role cards for the settings modal."""
    profiles = {}
    for profile_id, profile in COUNCIL_PROFILES.items():
        profiles[profile_id] = {
            "id": profile_id,
            "name": profile["name"],
            "perspective_roles": [
                {
                    "id": role["id"],
                    "name": role["name"],
                    "mandate": role.get("mandate", ""),
                    "must_include": role.get("must_include", []),
                }
                for role in profile.get("perspective_roles", [])
            ],
        }

    pairings = []
    for pairing in list_model_pairings():
        resolved = resolve_model_pairing(pairing["id"])
        pairings.append(
            {
                "id": pairing["id"],
                "label": pairing["label"],
                "description": pairing["description"],
                "council_models": resolved["council_models"],
                "chairman_model": resolved["chairman_model"],
                "interrogator_model": resolved["interrogator_model"],
            }
        )

    return {
        "default_model_pairing_id": DEFAULT_MODEL_PAIRING_ID,
        "pairings": pairings,
        "profiles": profiles,
    }


@app.get("/api/settings/free-models")
async def get_eligible_free_models():
    """List strict-zero-cost free models and key-eligible subset."""
    visible_models, visibility_err = await list_user_visible_models_with_error()
    if visible_models is None:
        return {
            "models": [],
            "filtered_models": [],
            "catalog_count": 0,
            "eligible_count": 0,
            "filtered_count": 0,
            "error": visibility_err,
            "catalog_error": None,
        }

    all_models, catalog_err = await list_models_with_error()
    if all_models is None:
        return {
            "models": [],
            "filtered_models": [],
            "catalog_count": 0,
            "eligible_count": 0,
            "filtered_count": 0,
            "error": None,
            "catalog_error": catalog_err,
        }

    by_id = {item.get("id"): item for item in all_models if item.get("id")}
    strict_catalog_ids = sorted(
        [
            model.get("id")
            for model in all_models
            if model.get("id") and _is_strict_zero_cost_free_model(model)
        ]
    )
    visible_set = set(visible_models)
    eligible_ids = [model_id for model_id in strict_catalog_ids if model_id in visible_set]
    filtered_ids = [model_id for model_id in strict_catalog_ids if model_id not in visible_set]

    models = [
        {
            "id": model_id,
            "context_length": (by_id.get(model_id) or {}).get("context_length"),
        }
        for model_id in eligible_ids
    ]
    filtered_models = [
        {
            "id": model_id,
            "context_length": (by_id.get(model_id) or {}).get("context_length"),
        }
        for model_id in filtered_ids
    ]
    return {
        "models": models,
        "filtered_models": filtered_models,
        "catalog_count": len(strict_catalog_ids),
        "eligible_count": len(eligible_ids),
        "filtered_count": len(filtered_ids),
        "error": None,
        "catalog_error": catalog_err,
    }


@app.get("/api/settings/privacy-safe-models")
async def get_privacy_safe_models():
    """List models allowed in Settings: visible paid + ZDR-compatible strict-free."""
    now = time.time()
    cached = PRIVACY_SAFE_MODELS_CACHE.get("payload")
    expires_at = float(PRIVACY_SAFE_MODELS_CACHE.get("expires_at") or 0.0)
    if cached and now < expires_at:
        return cached

    payload = await _build_privacy_safe_models_payload()
    PRIVACY_SAFE_MODELS_CACHE["payload"] = payload
    PRIVACY_SAFE_MODELS_CACHE["expires_at"] = now + 300.0
    return payload


@app.post("/api/settings/free-variant-check")
async def check_free_variant(request: FreeVariantCheckRequest):
    """Check if a model has a :free variant and whether it is key-eligible."""
    try:
        variant_model_id = _normalize_free_variant_model_id(request.model_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    visible_models, visibility_err = await list_user_visible_models_with_error()
    all_models, catalog_err = await list_models_with_error()

    if all_models is None:
        return {
            "input_model_id": request.model_id,
            "variant_model_id": variant_model_id,
            "status": "unknown",
            "in_catalog": None,
            "strict_zero_cost": None,
            "eligible": None,
            "hint": "Could not load model catalog from OpenRouter.",
            "visibility_error": visibility_err,
            "catalog_error": catalog_err,
        }

    by_id = {item.get("id"): item for item in all_models if item.get("id")}
    variant_metadata = by_id.get(variant_model_id)
    in_catalog = variant_metadata is not None
    strict_zero_cost = _is_strict_zero_cost_free_model(variant_metadata or {})

    if visible_models is None:
        return {
            "input_model_id": request.model_id,
            "variant_model_id": variant_model_id,
            "status": "unknown",
            "in_catalog": in_catalog,
            "strict_zero_cost": strict_zero_cost if in_catalog else None,
            "eligible": None,
            "hint": "Could not verify key-specific visibility from /models/user.",
            "visibility_error": visibility_err,
            "catalog_error": catalog_err,
        }

    eligible = variant_model_id in set(visible_models)
    if not in_catalog:
        status = "not_available"
        hint = "No explicit :free variant exists in the current OpenRouter catalog for this model."
    elif eligible:
        status = "available_and_eligible"
        hint = "This :free variant exists and is visible to your API key."
    else:
        status = "available_but_filtered"
        hint = "This :free variant exists but is filtered by your current routing/provider settings."

    return {
        "input_model_id": request.model_id,
        "variant_model_id": variant_model_id,
        "status": status,
        "in_catalog": in_catalog,
        "strict_zero_cost": strict_zero_cost if in_catalog else None,
        "eligible": eligible if in_catalog else False,
        "hint": hint,
        "visibility_error": None,
        "catalog_error": catalog_err,
    }


@app.post("/api/settings/test-pairing")
async def test_model_pairing(request: TestPairingRequest):
    """Probe each model in a pairing and return actionable diagnostics."""
    pairing = _resolve_pairing_or_400(request.model_pairing_id)
    pairing = await _apply_free_auto_router_override_or_400(
        pairing,
        request.free_backup_models_override,
    )
    probe_models = list(pairing["council_models"]) + [
        pairing["chairman_model"],
        pairing["interrogator_model"],
    ]
    unique_models = list(dict.fromkeys(probe_models))
    test_prompt = [{"role": "user", "content": "Reply with exactly: OK"}]

    eligibility_checks, eligibility_error = await _build_pairing_eligibility(pairing)
    eligible_map = {
        check["model"]: check.get("eligible")
        for check in eligibility_checks
    }

    checks = []
    all_passed = True
    for model in unique_models:
        preflight_eligible = eligible_map.get(model)
        if preflight_eligible is False:
            all_passed = False
            checks.append(
                {
                    "model": model,
                    "status": "blocked",
                    "error_type": "preflight_filtered",
                    "hint": "Model filtered by /models/user; adjust OpenRouter routing/preferences.",
                    "raw_error": None,
                    "latency_ms": 0,
                }
            )
            continue

        started = time.perf_counter()
        result, err = await query_model_with_error(model, test_prompt, timeout=20.0)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if result is not None:
            checks.append(
                {
                    "model": model,
                    "status": "pass",
                    "routed_model": result.get("model_used"),
                    "latency_ms": latency_ms,
                }
            )
            continue

        all_passed = False
        diagnosis = _diagnose_openrouter_failure(err or "")
        checks.append(
            {
                "model": model,
                "status": "fail",
                "error_type": diagnosis["error_type"],
                "raw_error": err,
                "hint": diagnosis["hint"],
                "latency_ms": latency_ms,
            }
        )

    return {
        "model_pairing_id": pairing["id"],
        "all_passed": all_passed,
        "checks": checks,
        "eligibility_error": eligibility_error,
    }


@app.get("/api/settings/model-pairings/{pairing_id}/eligibility")
async def get_model_pairing_eligibility(pairing_id: str):
    """Return eligibility/visibility for models in one pairing via /models/user."""
    pairing = _resolve_pairing_or_400(pairing_id)
    checks, error = await _build_pairing_eligibility(pairing)
    return {
        "model_pairing_id": pairing["id"],
        "checks": checks,
        "error": error,
    }


@app.get("/api/settings/model-pairings/{pairing_id}/diagnostics")
async def get_model_pairing_diagnostics(pairing_id: str):
    """Return runtime resolution diagnostics for transparent auto-substitution."""
    pairing = _resolve_pairing_or_400(pairing_id)
    eligibility_checks, eligibility_error = await _build_pairing_eligibility(pairing)
    runtime_pairing = await _resolve_runtime_pairing(pairing)
    return {
        "model_pairing_id": pairing["id"],
        "requested": runtime_pairing["requested"],
        "resolved": runtime_pairing["resolved"],
        "substitutions": runtime_pairing["substitutions"],
        "council_fallbacks": runtime_pairing["council_fallbacks"],
        "chairman_fallbacks": runtime_pairing["chairman_fallbacks"],
        "interrogator_fallbacks": runtime_pairing["interrogator_fallbacks"],
        "eligibility_checks": eligibility_checks,
        "eligibility_error": eligibility_error,
        "catalog_error": runtime_pairing["catalog_error"],
    }


@app.get("/api/profiles/{profile_id}/packets")
async def get_profile_packets(profile_id: str):
    """List locally stored research packets for a profile."""
    try:
        packets = storage.list_research_packets(profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"profile_id": profile_id, "packets": packets}


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Enrich assistant messages with deterministic local verdict-save status.
    messages = conversation.get("messages", [])
    for idx, message in enumerate(messages):
        if message.get("role") != "assistant" or not message.get("stage3"):
            continue
        existing = storage.get_saved_verdict_for_message(conversation, idx)
        if existing:
            message.setdefault("metadata", {})
            message["metadata"]["verdict_markdown"] = existing
    return conversation


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation from local history."""
    deleted = storage.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


@app.post("/api/conversations/{conversation_id}/verdict")
async def save_verdict_markdown(conversation_id: str, request: SaveVerdictRequest):
    """Save a specific assistant Stage 3 answer to markdown."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = conversation.get("messages", [])
    idx = request.assistant_message_index
    if idx < 0 or idx >= len(messages):
        raise HTTPException(status_code=400, detail="Invalid assistant_message_index")

    message = messages[idx]
    if message.get("role") != "assistant" or not message.get("stage3"):
        raise HTTPException(status_code=400, detail="Selected message has no Stage 3 verdict")

    existing = storage.get_saved_verdict_for_message(conversation, idx)
    if existing:
        return {
            **existing,
            "already_saved": True,
        }

    saved = storage.save_verdict_markdown(
        conversation,
        message["stage3"],
        assistant_message_index=idx,
        interrogation=message.get("interrogation"),
        metadata=message.get("metadata"),
    )
    message.setdefault("metadata", {})
    message["metadata"]["verdict_markdown"] = saved
    storage.save_conversation(conversation)
    return {
        **saved,
        "already_saved": False,
    }


@app.post("/api/conversations/{conversation_id}/interrogation/start")
async def start_interrogation(conversation_id: str, request: StartInterrogationRequest):
    """
    Start Stage 0 interrogation for the first message in a conversation.
    Returns the first interrogator question and a session id.
    """
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if len(conversation.get("messages", [])) != 0:
        raise HTTPException(
            status_code=400,
            detail="Interrogation is only available for the first message in a conversation",
        )

    profile_id = (request.profile_id or DEFAULT_PROFILE_ID).strip()
    try:
        profile = get_profile(profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        packet = storage.load_research_packet(profile_id, request.packet_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pairing = _resolve_pairing_or_400(request.model_pairing_id)
    pairing = await _apply_free_auto_router_override_or_400(
        pairing,
        request.free_backup_models_override,
    )
    runtime_pairing = await _resolve_runtime_pairing(pairing)
    interrogator_model = runtime_pairing["resolved"]["interrogator_model"]

    # Remove stale sessions for this conversation (e.g. canceled modal on client).
    stale_ids = [
        session_id
        for session_id, data in INTERROGATION_SESSIONS.items()
        if data.get("conversation_id") == conversation_id
    ]
    for session_id in stale_ids:
        INTERROGATION_SESSIONS.pop(session_id, None)

    first_question, err = await generate_interrogator_question(
        request.content,
        [],
        run_context={"profile": profile, "research_packet": packet},
        min_questions=INTERROGATOR_MIN_QUESTIONS,
        max_questions=INTERROGATOR_MAX_QUESTIONS,
        interrogator_model=interrogator_model,
    )
    if not first_question:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate interrogator question: {err or 'unknown error'}",
        )

    session_id = str(uuid.uuid4())
    INTERROGATION_SESSIONS[session_id] = {
        "conversation_id": conversation_id,
        "content": request.content,
        "min_questions": INTERROGATOR_MIN_QUESTIONS,
        "max_questions": INTERROGATOR_MAX_QUESTIONS,
        "model": interrogator_model,
        "model_pairing_id": pairing["id"],
        "model_resolution": runtime_pairing,
        "profile_id": profile_id,
        "profile_name": profile["name"],
        "packet_id": packet["packet_id"],
        "packet_title": packet.get("title"),
        "packet_as_of": packet.get("as_of"),
        "research_packet": packet,
        "steps": [
            {
                "question": first_question,
                "answer": None,
                "deferred": False,
            }
        ],
    }

    return {
        "session_id": session_id,
        "model": interrogator_model,
        "model_pairing_id": pairing["id"],
        "model_resolution": runtime_pairing,
        "profile_id": profile_id,
        "profile_name": profile["name"],
        "packet_id": packet["packet_id"],
        "packet_title": packet.get("title"),
        "packet_as_of": packet.get("as_of"),
        "min_questions": INTERROGATOR_MIN_QUESTIONS,
        "max_questions": INTERROGATOR_MAX_QUESTIONS,
        "question_number": 1,
        "question": first_question,
    }


def _build_interrogation_payload(session: Dict[str, Any]) -> Dict[str, Any]:
    """Build the completed interrogation payload from session state."""
    steps = session["steps"]
    return {
        "model": session["model"],
        "profile_id": session["profile_id"],
        "profile_name": session.get("profile_name"),
        "packet_id": session.get("packet_id"),
        "packet_title": session.get("packet_title"),
        "packet_as_of": session.get("packet_as_of"),
        "min_questions": session["min_questions"],
        "max_questions": session["max_questions"],
        "questions_asked": len(steps),
        "steps": steps,
        "summary": session.get("summary", ""),
        "coverage": session.get("coverage"),
        "completed": True,
        "run_context": {
            "model_pairing_id": session.get("model_pairing_id"),
            "model_resolution": session.get("model_resolution"),
            "profile_id": session["profile_id"],
            "profile": get_profile(session["profile_id"]),
            "packet_id": session.get("packet_id"),
            "packet_title": session.get("packet_title"),
            "packet_as_of": session.get("packet_as_of"),
            "research_packet": session.get("research_packet"),
            "role_assignments": [],
        },
    }


@app.post("/api/conversations/{conversation_id}/interrogation/answer")
async def answer_interrogation(conversation_id: str, request: AnswerInterrogationRequest):
    """
    Submit an answer for the active interrogation session and receive either:
    - the next question (with coverage assessment),
    - a confirmation summary for high-uncertainty runs, or
    - a completed interrogation transcript payload.
    """
    session = INTERROGATION_SESSIONS.get(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Interrogation session not found")
    if session["conversation_id"] != conversation_id:
        raise HTTPException(status_code=400, detail="Session does not belong to this conversation")

    steps = session["steps"]
    if not steps or steps[-1].get("answer") is not None:
        raise HTTPException(status_code=400, detail="No pending interrogation question")

    raw_answer = (request.answer or "").strip()
    if not raw_answer:
        raise HTTPException(status_code=400, detail="Answer cannot be empty")

    deferred = is_defer_answer(raw_answer)
    normalized_answer = "Deferred to council" if deferred else raw_answer
    steps[-1]["answer"] = normalized_answer
    steps[-1]["deferred"] = deferred

    profile = get_profile(session["profile_id"])
    required_fields = profile.get("required_context_fields", [])

    assessment = await assess_interrogation_coverage(
        session["content"],
        steps,
        required_fields,
        min_questions=session["min_questions"],
        max_questions=session["max_questions"],
        interrogator_model=session["model"],
    )

    session["coverage"] = assessment.get("coverage")
    decision = assessment.get("decision", "stop_sufficient")

    if decision == "ask_next":
        next_question = assessment.get("next_question") or ""
        if not next_question:
            next_question_fallback, _ = await generate_interrogator_question(
                session["content"],
                steps,
                run_context={"profile": profile, "research_packet": session.get("research_packet")},
                min_questions=session["min_questions"],
                max_questions=session["max_questions"],
                interrogator_model=session["model"],
            )
            next_question = next_question_fallback or "What is the most important constraint we should respect?"
        steps.append({"question": next_question, "answer": None, "deferred": False})
        return {
            "done": False,
            "question_number": len(steps),
            "question": next_question,
            "coverage": assessment.get("coverage"),
            "note": assessment.get("error"),
        }

    summary = await summarize_interrogation(
        session["content"],
        steps,
        interrogator_model=session["model"],
    )
    session["summary"] = summary

    if decision == "confirm_needed":
        confirmation_summary = assessment.get("confirmation_summary") or summary
        session["awaiting_confirmation"] = True
        session["confirmation_summary"] = confirmation_summary
        return {
            "done": False,
            "awaiting_confirmation": True,
            "confirmation_summary": confirmation_summary,
            "coverage": assessment.get("coverage"),
        }

    interrogation = _build_interrogation_payload(session)
    INTERROGATION_SESSIONS.pop(request.session_id, None)
    return {"done": True, "interrogation": interrogation}


@app.post("/api/conversations/{conversation_id}/interrogation/confirm")
async def confirm_interrogation(conversation_id: str, request: ConfirmInterrogationRequest):
    """
    Confirm or reject the interrogation summary.
    If confirmed, returns the completed interrogation payload.
    If rejected, returns the user to questioning with one more attempt.
    """
    session = INTERROGATION_SESSIONS.get(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Interrogation session not found")
    if session["conversation_id"] != conversation_id:
        raise HTTPException(status_code=400, detail="Session does not belong to this conversation")
    if not session.get("awaiting_confirmation"):
        raise HTTPException(status_code=400, detail="Session is not awaiting confirmation")

    session["awaiting_confirmation"] = False

    if request.confirmed:
        interrogation = _build_interrogation_payload(session)
        INTERROGATION_SESSIONS.pop(request.session_id, None)
        return {"done": True, "interrogation": interrogation}

    profile = get_profile(session["profile_id"])
    steps = session["steps"]
    next_question, err = await generate_interrogator_question(
        session["content"],
        steps,
        run_context={"profile": profile, "research_packet": session.get("research_packet")},
        min_questions=session["min_questions"],
        max_questions=session["max_questions"] + 1,
        interrogator_model=session["model"],
    )
    if not next_question:
        interrogation = _build_interrogation_payload(session)
        INTERROGATION_SESSIONS.pop(request.session_id, None)
        return {"done": True, "interrogation": interrogation}

    session["max_questions"] = session["max_questions"] + 1
    steps.append({"question": next_question, "answer": None, "deferred": False})
    return {
        "done": False,
        "question_number": len(steps),
        "question": next_question,
        "coverage": session.get("coverage"),
        "note": "Additional question after confirmation rejection",
    }


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    pairing = _resolve_pairing_or_400(request.model_pairing_id)
    pairing = await _apply_free_auto_router_override_or_400(
        pairing,
        request.free_backup_models_override,
    )
    runtime_pairing = await _resolve_runtime_pairing(pairing)
    is_first_message, interrogation, run_context = _resolve_message_context(conversation, request)
    if run_context is None:
        run_context = {}
    run_context["model_resolution"] = runtime_pairing
    council_models_for_run = _merge_council_models_with_role_override(
        runtime_pairing["resolved"]["council_models"],
        run_context.get("profile"),
        request.role_assignments_override,
    )
    try:
        _validate_role_assignment_override(
            run_context,
            council_models_for_run,
            request.role_assignments_override,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process
    try:
        stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
            request.content,
            interrogation=interrogation,
            run_context=run_context,
            council_models=council_models_for_run,
            chairman_model=runtime_pairing["resolved"]["chairman_model"],
            model_pairing_id=pairing["id"],
            role_assignments_override=request.role_assignments_override,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result,
        interrogation=interrogation,
        metadata=metadata,
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    pairing = _resolve_pairing_or_400(request.model_pairing_id)
    pairing = await _apply_free_auto_router_override_or_400(
        pairing,
        request.free_backup_models_override,
    )
    runtime_pairing = await _resolve_runtime_pairing(pairing)
    is_first_message, interrogation, run_context = _resolve_message_context(conversation, request)
    if run_context is None:
        run_context = {}
    run_context["model_resolution"] = runtime_pairing
    council_models_for_run = _merge_council_models_with_role_override(
        runtime_pairing["resolved"]["council_models"],
        run_context.get("profile"),
        request.role_assignments_override,
    )
    try:
        _validate_role_assignment_override(
            run_context,
            council_models_for_run,
            request.role_assignments_override,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def event_generator():
        title_task = None
        run_task = None
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))
            event_queue: asyncio.Queue = asyncio.Queue()

            async def enqueue_progress(event: Dict[str, Any]):
                await event_queue.put(event)

            run_task = asyncio.create_task(
                run_full_council(
                    request.content,
                    interrogation=interrogation,
                    run_context=run_context,
                    progress_callback=enqueue_progress,
                    council_models=council_models_for_run,
                    chairman_model=runtime_pairing["resolved"]["chairman_model"],
                    model_pairing_id=pairing["id"],
                    role_assignments_override=request.role_assignments_override,
                )
            )

            while True:
                if run_task.done() and event_queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                yield f"data: {json.dumps(event)}\n\n"

            stage1_results, stage2_results, stage3_result, metadata = await run_task

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
                interrogation=interrogation,
                metadata=metadata,
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            if run_task and not run_task.done():
                run_task.cancel()
            if title_task and not title_task.done():
                title_task.cancel()
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=BACKEND_PORT)
