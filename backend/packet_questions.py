"""Pure helpers for research-packet open-question tracking in Stage 0.

No I/O and no LLM calls. Used by the interrogator to decide which packet
open questions remain unaddressed by the interrogation transcript.
"""

import re
from typing import Any, Dict, List

# Small stopword set aligned with the diagnostics overlap estimator.
_STOPWORDS = {
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
    "does",
    "into",
    "than",
    "them",
    "then",
    "they",
}

# Rule: an open question counts as "addressed" when at least 35% of its
# content tokens (minimum 2 shared tokens) appear in an asked question.
_ADDRESSED_MIN_RATIO = 0.35
_ADDRESSED_MIN_SHARED = 2


def _content_tokens(text: str) -> set:
    """Lowercase alphabetic tokens of length >= 4, minus stopwords."""
    tokens = set(re.findall(r"[a-zA-Z]{4,}", (text or "").lower()))
    return tokens - _STOPWORDS


def packet_open_question_was_addressed(question_text: str, open_question: str) -> bool:
    """
    Deterministic check that an asked question targets a packet open question.

    Addressed when shared content tokens >= 2 and cover >= 35% of the open
    question's content tokens. Falls back to substring match when the open
    question has fewer than 2 content tokens.
    """
    oq_tokens = _content_tokens(open_question)
    if len(oq_tokens) < _ADDRESSED_MIN_SHARED:
        needle = (open_question or "").strip().lower().rstrip("?.! ")
        return bool(needle) and needle in (question_text or "").lower()

    asked_tokens = _content_tokens(question_text)
    shared = oq_tokens & asked_tokens
    if len(shared) < _ADDRESSED_MIN_SHARED:
        return False
    return (len(shared) / len(oq_tokens)) >= _ADDRESSED_MIN_RATIO


def unresolved_packet_open_questions(
    packet: Dict[str, Any] | None,
    steps: List[Dict[str, Any]] | None,
) -> List[str]:
    """
    Return packet open questions not yet addressed by any transcript question.

    Preserves packet order. Returns [] when the packet is missing or has no
    open questions.
    """
    open_questions = [
        oq.strip()
        for oq in ((packet or {}).get("open_questions") or [])
        if isinstance(oq, str) and oq.strip()
    ]
    if not open_questions:
        return []

    asked = [step.get("question", "") for step in (steps or [])]
    unresolved = []
    for oq in open_questions:
        if not any(packet_open_question_was_addressed(q, oq) for q in asked):
            unresolved.append(oq)
    return unresolved
