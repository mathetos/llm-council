"""JSON-based storage for conversations."""

import json
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from .config import DATA_DIR, RESEARCH_PACKETS_DIR, get_profile

VERDICTS_DIR = "data/verdicts"


def ensure_data_dir():
    """Ensure the data directory exists."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str) -> str:
    """Get the file path for a conversation."""
    return os.path.join(DATA_DIR, f"{conversation_id}.json")


def ensure_verdicts_dir():
    """Ensure the verdicts directory exists."""
    Path(VERDICTS_DIR).mkdir(parents=True, exist_ok=True)


def ensure_research_packets_dir():
    """Ensure the local research packet directory exists."""
    Path(RESEARCH_PACKETS_DIR).mkdir(parents=True, exist_ok=True)


def _slugify_filename(value: str) -> str:
    """Create a human-readable safe filename stem."""
    stem = value.lower().strip()
    stem = re.sub(r"[^a-z0-9\s-]", "", stem)
    stem = re.sub(r"[\s_-]+", "-", stem).strip("-")
    return stem or "verdict"


def _next_available_verdict_path(stem: str) -> str:
    """Return a unique markdown path in the verdicts directory."""
    candidate = os.path.join(VERDICTS_DIR, f"{stem}.md")
    if not os.path.exists(candidate):
        return candidate

    suffix = 2
    while True:
        candidate = os.path.join(VERDICTS_DIR, f"{stem}-{suffix}.md")
        if not os.path.exists(candidate):
            return candidate
        suffix += 1


def _deterministic_verdict_filename(
    conversation_id: str,
    assistant_message_index: int,
    title: str,
) -> str:
    """Build a stable verdict filename for a specific assistant message."""
    stem = _slugify_filename(title)
    conv_short = (conversation_id or "conversation")[:8]
    return f"{stem}-{conv_short}-a{assistant_message_index + 1}.md"


def _deterministic_verdict_path(
    conversation_id: str,
    assistant_message_index: int,
    title: str,
) -> str:
    """Resolve deterministic verdict path for one assistant message."""
    filename = _deterministic_verdict_filename(conversation_id, assistant_message_index, title)
    return os.path.join(VERDICTS_DIR, filename)


def get_saved_verdict_for_message(
    conversation: Dict[str, Any],
    assistant_message_index: int,
) -> Optional[Dict[str, str]]:
    """Return existing saved verdict metadata for a specific assistant message, if present."""
    ensure_verdicts_dir()
    title = conversation.get("title", "verdict")
    conversation_id = conversation.get("id", "unknown")
    path = _deterministic_verdict_path(conversation_id, assistant_message_index, title)
    if not os.path.exists(path):
        return None
    return {
        "path": path,
        "relative_path": path.replace("\\", "/"),
        "filename": os.path.basename(path),
    }


def _packet_profile_dir(profile_id: str) -> str:
    return os.path.join(RESEARCH_PACKETS_DIR, profile_id)


def _validate_packet_schema(packet: Dict[str, Any], profile_id: str) -> None:
    """Validate a local research packet contract."""
    required_keys = {
        "packet_id",
        "profile_id",
        "title",
        "as_of",
        "summary",
        "facts",
        "assumptions",
        "constraints",
        "open_questions",
        "references",
    }
    missing = required_keys - set(packet.keys())
    if missing:
        raise ValueError(f"Research packet missing keys: {sorted(missing)}")
    if packet["profile_id"] != profile_id:
        raise ValueError(
            f"Research packet profile_id mismatch: expected '{profile_id}', got '{packet['profile_id']}'"
        )
    if not isinstance(packet["facts"], list) or not packet["facts"]:
        raise ValueError("Research packet 'facts' must be a non-empty list")
    for idx, fact in enumerate(packet["facts"]):
        if not isinstance(fact, dict):
            raise ValueError(f"Research packet fact at index {idx} must be an object")
        if not {"statement", "confidence"} <= set(fact.keys()):
            raise ValueError(f"Research packet fact at index {idx} missing statement/confidence")
        if fact["confidence"] not in {"high", "medium", "low"}:
            raise ValueError(
                f"Research packet fact at index {idx} has invalid confidence '{fact['confidence']}'"
            )

    for key in ("assumptions", "constraints", "open_questions", "references"):
        if not isinstance(packet[key], list):
            raise ValueError(f"Research packet '{key}' must be a list")


def list_research_packets(profile_id: str) -> List[Dict[str, str]]:
    """List available packet metadata for a profile."""
    get_profile(profile_id)  # validates profile_id
    ensure_research_packets_dir()
    profile_dir = _packet_profile_dir(profile_id)
    if not os.path.isdir(profile_dir):
        return []

    packets: List[Dict[str, str]] = []
    for filename in sorted(os.listdir(profile_dir)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(profile_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            packet = json.load(f)
        _validate_packet_schema(packet, profile_id)
        packets.append(
            {
                "packet_id": packet["packet_id"],
                "title": packet["title"],
                "as_of": packet["as_of"],
                "summary": packet["summary"],
                "file": filename,
            }
        )
    return packets


def load_research_packet(profile_id: str, packet_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Load a local research packet for the selected profile.

    Resolution:
    - packet_id provided: load `<profile>/<packet_id>.json`
    - packet_id omitted: prefer `<profile>/default.json`, else first packet by filename
    """
    get_profile(profile_id)  # validates profile_id
    ensure_research_packets_dir()
    profile_dir = _packet_profile_dir(profile_id)
    if not os.path.isdir(profile_dir):
        raise ValueError(
            f"No research packet directory for profile '{profile_id}'. "
            f"Expected: {profile_dir}"
        )

    if packet_id:
        filename = f"{packet_id}.json"
        path = os.path.join(profile_dir, filename)
        if not os.path.exists(path):
            raise ValueError(
                f"Research packet '{packet_id}' not found for profile '{profile_id}'"
            )
    else:
        default_path = os.path.join(profile_dir, "default.json")
        if os.path.exists(default_path):
            path = default_path
        else:
            candidates = sorted(
                fn for fn in os.listdir(profile_dir) if fn.endswith(".json")
            )
            if not candidates:
                raise ValueError(
                    f"No research packets found for profile '{profile_id}' in {profile_dir}"
                )
            path = os.path.join(profile_dir, candidates[0])

    with open(path, "r", encoding="utf-8") as f:
        packet = json.load(f)

    _validate_packet_schema(packet, profile_id)
    packet["_source_path"] = path
    return packet


def create_conversation(conversation_id: str) -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        New conversation dict
    """
    ensure_data_dir()

    conversation = {
        "id": conversation_id,
        "created_at": datetime.utcnow().isoformat(),
        "title": "New Conversation",
        "messages": []
    }

    # Save to file
    path = get_conversation_path(conversation_id)
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)

    return conversation


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a conversation from storage.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        Conversation dict or None if not found
    """
    path = get_conversation_path(conversation_id)

    if not os.path.exists(path):
        return None

    with open(path, 'r') as f:
        return json.load(f)


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation JSON file if it exists."""
    path = get_conversation_path(conversation_id)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


def save_conversation(conversation: Dict[str, Any]):
    """
    Save a conversation to storage.

    Args:
        conversation: Conversation dict to save
    """
    ensure_data_dir()

    path = get_conversation_path(conversation['id'])
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)


def list_conversations() -> List[Dict[str, Any]]:
    """
    List all conversations (metadata only).

    Returns:
        List of conversation metadata dicts
    """
    ensure_data_dir()

    conversations = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json'):
            path = os.path.join(DATA_DIR, filename)
            with open(path, 'r') as f:
                data = json.load(f)
                # Return metadata only
                conversations.append({
                    "id": data["id"],
                    "created_at": data["created_at"],
                    "title": data.get("title", "New Conversation"),
                    "message_count": len(data["messages"])
                })

    # Sort by creation time, newest first
    conversations.sort(key=lambda x: x["created_at"], reverse=True)

    return conversations


def add_user_message(conversation_id: str, content: str):
    """
    Add a user message to a conversation.

    Args:
        conversation_id: Conversation identifier
        content: User message content
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["messages"].append({
        "role": "user",
        "content": content
    })

    save_conversation(conversation)


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
    interrogation: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Add an assistant message with all 3 stages to a conversation.

    Args:
        conversation_id: Conversation identifier
        stage1: List of individual model responses
        stage2: List of model rankings
        stage3: Final synthesized response
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    assistant_message = {
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
    }
    if interrogation:
        assistant_message["interrogation"] = interrogation
    if metadata:
        assistant_message["metadata"] = metadata

    conversation["messages"].append(assistant_message)

    save_conversation(conversation)


def update_conversation_title(conversation_id: str, title: str):
    """
    Update the title of a conversation.

    Args:
        conversation_id: Conversation identifier
        title: New title for the conversation
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["title"] = title
    save_conversation(conversation)


def save_verdict_markdown(
    conversation: Dict[str, Any],
    stage3: Dict[str, Any],
    assistant_message_index: Optional[int] = None,
    interrogation: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Save a Stage 3 verdict to markdown with a human-readable filename.

    Returns:
        Dict with absolute and relative file path info.
    """
    ensure_verdicts_dir()

    title = conversation.get("title", "verdict")
    if assistant_message_index is not None:
        path = _deterministic_verdict_path(
            conversation.get("id", "unknown"),
            assistant_message_index,
            title,
        )
    else:
        stem = _slugify_filename(title)
        path = _next_available_verdict_path(stem)

    chairman = stage3.get("model", "unknown")
    response = stage3.get("response", "").strip()
    created_at = datetime.utcnow().isoformat()

    markdown = (
        f"# {title}\n\n"
        f"- Conversation ID: `{conversation.get('id', 'unknown')}`\n"
        f"- Saved At (UTC): `{created_at}`\n"
        f"- Chairman Model: `{chairman}`\n\n"
    )

    if interrogation and interrogation.get("steps"):
        summary = (interrogation.get("summary") or "").strip()
        markdown += "## Interrogation Context\n\n"
        markdown += f"- Interrogator Model: `{interrogation.get('model', 'unknown')}`\n"
        markdown += (
            f"- Questions Asked: `{interrogation.get('questions_asked', len(interrogation.get('steps', [])))}` "
            f"(Configured min/max `{interrogation.get('min_questions', '?')}`/"
            f"`{interrogation.get('max_questions', '?')}`)\n\n"
        )
        if summary:
            markdown += "### Summary\n\n"
            markdown += summary + "\n\n"

        markdown += "### Transcript\n\n"
        for idx, step in enumerate(interrogation["steps"], start=1):
            markdown += f"**Q{idx}.** {step.get('question', '').strip()}\n\n"
            if step.get("deferred"):
                markdown += f"**A{idx}.** _Deferred to council._\n\n"
            else:
                markdown += f"**A{idx}.** {step.get('answer', '').strip()}\n\n"

    run_context = (metadata or {}).get("run_context") if metadata else None
    if run_context:
        markdown += "## Profile Guardrails Context\n\n"
        markdown += f"- Profile: `{run_context.get('profile_id', 'unknown')}`\n"
        markdown += f"- Research Packet: `{run_context.get('packet_id', 'unknown')}`\n"
        if run_context.get("packet_title"):
            markdown += f"- Packet Title: {run_context['packet_title']}\n"
        if run_context.get("packet_as_of"):
            markdown += f"- Packet As Of: `{run_context['packet_as_of']}`\n"
        markdown += "\n"

    role_assignments = (metadata or {}).get("role_assignments") if metadata else None
    if role_assignments:
        markdown += "## Perspective Assignments\n\n"
        for assignment in role_assignments:
            markdown += (
                f"- `{assignment.get('model', 'unknown')}` -> "
                f"`{assignment.get('role_name', assignment.get('role_id', 'unknown'))}`\n"
            )
        markdown += "\n"

    guardrail_status = (metadata or {}).get("guardrail_status") if metadata else None
    if guardrail_status:
        markdown += "## Guardrail Status\n\n"
        markdown += f"- Status: `{guardrail_status.get('status', 'unknown')}`\n"
        violations = guardrail_status.get("violations") or []
        if violations:
            markdown += "- Violations:\n"
            for violation in violations:
                markdown += f"  - {violation}\n"
        markdown += "\n"

    telemetry = (metadata or {}).get("telemetry") if metadata else None
    if telemetry:
        markdown += "## Telemetry\n\n"
        if telemetry.get("total_ms") is not None:
            markdown += f"- Total runtime: `{telemetry['total_ms']}ms`\n"
        for stage_key in ("stage1_ms", "stage2_ms", "stage3_ms"):
            if telemetry.get(stage_key) is not None:
                markdown += f"- {stage_key.replace('_ms', '').replace('_', ' ').title()}: `{telemetry[stage_key]}ms`\n"
        total_usage = telemetry.get("total_usage") or {}
        if total_usage.get("total_tokens"):
            markdown += f"- Total tokens: `{total_usage['total_tokens']}`\n"
        if total_usage.get("total_cost") is not None:
            markdown += f"- Total cost: `${total_usage['total_cost']}`\n"
        markdown += "\n"

    markdown += (
        "## Final Council Answer\n\n"
        f"{response}\n"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)

    return {
        "path": path,
        "relative_path": path.replace("\\", "/"),
        "filename": os.path.basename(path),
    }
