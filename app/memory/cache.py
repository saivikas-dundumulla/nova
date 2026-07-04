from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.config.settings import Settings, get_settings
from app.memory import store

# A small stopword set so common filler words don't inflate similarity.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "to", "of", "and", "or", "in",
    "on", "for", "with", "how", "do", "i", "my", "me", "can", "you", "please", "help",
    "what", "why", "when", "it", "this", "that", "get", "getting", "am", "we", "our",
}
_WORD = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> list[str]:
    tokens = _WORD.findall((text or "").lower())
    return [t for t in tokens if t not in _STOPWORDS]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def similarity(q1: str, q2: str) -> float:
    """Blended lexical similarity in [0, 1]: token-set Jaccard + sequence ratio."""
    t1, t2 = normalize(q1), normalize(q2)
    if not t1 or not t2:
        return 0.0
    jac = _jaccard(set(t1), set(t2))
    seq = SequenceMatcher(None, " ".join(t1), " ".join(t2)).ratio()
    return 0.6 * jac + 0.4 * seq


def find_cached_answer(
    user_id: str,
    question: str,
    *,
    incident_number: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Return the best past answer for this user whose question is similar enough, else None.

    Matching is scoped per user. When an incident number is present, only past turns for the
    same incident are considered (so answers never leak across incidents).
    """
    s = settings or get_settings()
    if not s.cache_enabled:
        return None
    if len((question or "").strip()) < s.cache_min_question_chars:
        return None

    best: dict[str, Any] | None = None
    best_score = 0.0
    for pair in store.iter_qa_pairs(user_id, s):
        if (pair.get("incident_number") or None) != (incident_number or None):
            continue
        if not (pair.get("answer") or "").strip():
            continue
        score = similarity(question, pair.get("question", ""))
        if score > best_score:
            best_score, best = score, pair

    if best is None or best_score < s.cache_similarity_threshold:
        return None
    return {
        "answer": best["answer"],
        "references": best.get("references", []),
        "matched_question": best.get("question", ""),
        "score": round(best_score, 3),
        "thread_id": best.get("thread_id"),
    }
