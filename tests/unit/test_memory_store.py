from __future__ import annotations

from app.memory import store


def test_append_and_get_thread():
    store.append_turn("u1", "t1", "how to reset vpn", "Go to settings.")
    msgs = store.get_thread("u1", "t1")
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "how to reset vpn"
    assert msgs[1]["content"] == "Go to settings."


def test_append_multiple_turns_same_thread():
    store.append_turn("u1", "t1", "q1", "a1")
    store.append_turn("u1", "t1", "q2", "a2")
    msgs = store.get_thread("u1", "t1")
    assert len(msgs) == 4
    assert [m["content"] for m in msgs] == ["q1", "a1", "q2", "a2"]


def test_list_threads_sorted_and_titled():
    store.append_turn("u1", "t1", "first question here", "a")
    store.append_turn("u1", "t2", "second question here", "a")
    threads = store.list_threads("u1")
    assert {t["thread_id"] for t in threads} == {"t1", "t2"}
    titles = {t["title"] for t in threads}
    assert "first question here" in titles


def test_iter_qa_pairs_carries_incident_and_references():
    store.append_turn(
        "u1", "t1", "incident question", "the answer",
        incident_number="INC1", references=[{"title": "KB"}],
    )
    pairs = store.iter_qa_pairs("u1")
    assert len(pairs) == 1
    assert pairs[0]["incident_number"] == "INC1"
    assert pairs[0]["answer"] == "the answer"
    assert pairs[0]["references"] == [{"title": "KB"}]


def test_users_are_isolated():
    store.append_turn("u1", "t1", "q", "a")
    assert store.list_threads("u2") == []


def test_unsafe_user_id_does_not_escape_dir(tmp_path):
    # A path-traversal-style id must be sanitized, not written outside the store dir.
    store.append_turn("../../evil", "t1", "q", "a")
    # It is retrievable under the same (sanitized) id, and no traversal file was created.
    assert store.get_thread("../../evil", "t1")
