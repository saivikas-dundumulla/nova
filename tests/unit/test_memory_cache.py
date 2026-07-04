from __future__ import annotations

from app.config.settings import get_settings
from app.memory import store
from app.memory.cache import find_cached_answer, similarity


def test_similarity_high_for_near_identical():
    assert similarity("how do I reset my VPN password", "how to reset the VPN password") > 0.7


def test_similarity_low_for_unrelated():
    assert similarity("reset vpn password", "book a meeting room") < 0.3


def test_cache_hit_on_repeat_question():
    store.append_turn("u1", "t1", "how do I reset my VPN password?", "Open Settings → Reset.")
    hit = find_cached_answer("u1", "how to reset my VPN password")
    assert hit is not None
    assert hit["answer"] == "Open Settings → Reset."
    assert hit["score"] >= get_settings().cache_similarity_threshold


def test_cache_miss_on_unrelated_question():
    store.append_turn("u1", "t1", "how do I reset my VPN password?", "Open Settings → Reset.")
    assert find_cached_answer("u1", "where is the cafeteria located today") is None


def test_cache_respects_min_question_length():
    store.append_turn("u1", "t1", "vpn", "answer")
    assert find_cached_answer("u1", "vpn") is None  # too short to match safely


def test_cache_is_scoped_per_incident():
    store.append_turn("o1", "t1", "what is the resolution", "Restart the service.", incident_number="INC1")
    # Same question text but a different incident must NOT reuse the answer.
    assert find_cached_answer("o1", "what is the resolution", incident_number="INC2") is None
    # Same incident does reuse it.
    hit = find_cached_answer("o1", "what is the resolution", incident_number="INC1")
    assert hit is not None and hit["answer"] == "Restart the service."


def test_cache_disabled_returns_none(monkeypatch):
    store.append_turn("u1", "t1", "how do I reset my VPN password?", "Open Settings.")
    settings = get_settings()
    monkeypatch.setattr(settings, "cache_enabled", False)
    assert find_cached_answer("u1", "how do I reset my VPN password?") is None
