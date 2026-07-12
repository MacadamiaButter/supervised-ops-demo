"""Inquiry lifecycle with the LLM mocked -- classification routing,
draft/approve/edit/reject transitions, and the audit trail they produce.
No network call is made anywhere in this file.
"""

from app import audit, llm, pipeline
from app.db import create_inquiry, get_inquiry


def _make_inquiry(text="My sink is leaking under the cabinet."):
    return create_inquiry(
        customer_name="Test Customer",
        customer_contact="test@example.com",
        channel="webform",
        raw_text=text,
    )


def test_high_confidence_clean_path_gets_drafted(monkeypatch):
    monkeypatch.setattr(
        llm, "classify",
        lambda text: llm.LLMResult(ok=True, parsed={"category": "maintenance_request", "urgency": "med", "confidence": 0.9}),
    )
    monkeypatch.setattr(llm, "draft_reply", lambda *a, **k: llm.LLMResult(ok=True, content="Draft reply text."))

    iid = _make_inquiry()
    pipeline.process_new_inquiry(iid)

    row = get_inquiry(iid)
    assert row["status"] == "drafted"
    assert row["draft_text"] == "Draft reply text."
    events = [e["event"] for e in audit.read_events(reverse=False)]
    assert events == ["received", "classified", "drafted"]


def test_low_confidence_escalates_without_drafting(monkeypatch):
    monkeypatch.setattr(
        llm, "classify",
        lambda text: llm.LLMResult(ok=True, parsed={"category": "other", "urgency": "low", "confidence": 0.4}),
    )
    called = {"draft": False}

    def fake_draft(*a, **k):
        called["draft"] = True
        return llm.LLMResult(ok=True, content="should not happen")

    monkeypatch.setattr(llm, "draft_reply", fake_draft)

    iid = _make_inquiry()
    pipeline.process_new_inquiry(iid)

    row = get_inquiry(iid)
    assert row["status"] == "needs_human"
    assert row["draft_text"] is None
    assert called["draft"] is False
    events = [e["event"] for e in audit.read_events(reverse=False)]
    assert events == ["received", "classified", "escalated"]


def test_high_urgency_complaint_escalates_even_with_high_confidence(monkeypatch):
    monkeypatch.setattr(
        llm, "classify",
        lambda text: llm.LLMResult(ok=True, parsed={"category": "complaint", "urgency": "high", "confidence": 0.97}),
    )
    monkeypatch.setattr(llm, "draft_reply", lambda *a, **k: llm.LLMResult(ok=True, content="unused"))

    iid = _make_inquiry("This is the third time I've complained!")
    pipeline.process_new_inquiry(iid)

    row = get_inquiry(iid)
    assert row["status"] == "needs_human"


def test_brain_unavailable_fails_soft_to_needs_human(monkeypatch):
    monkeypatch.setattr(llm, "classify", lambda text: llm.LLMResult(ok=False, error="brain unreachable"))

    iid = _make_inquiry()
    pipeline.process_new_inquiry(iid)

    row = get_inquiry(iid)
    assert row["status"] == "needs_human"
    events = [e for e in audit.read_events(reverse=False)]
    assert events[-1]["event"] == "escalated"
    assert events[-1]["details"]["reason"] == "ai_unavailable"


def test_approve_marks_replied_with_draft_as_final(monkeypatch):
    monkeypatch.setattr(
        llm, "classify",
        lambda text: llm.LLMResult(ok=True, parsed={"category": "leasing_inquiry", "urgency": "low", "confidence": 0.9}),
    )
    monkeypatch.setattr(llm, "draft_reply", lambda *a, **k: llm.LLMResult(ok=True, content="Here is a draft."))
    iid = _make_inquiry()
    pipeline.process_new_inquiry(iid)

    pipeline.approve(iid)
    row = get_inquiry(iid)
    assert row["status"] == "replied"
    assert row["final_text"] == "Here is a draft."
    assert row["reply_kind"] == "approved"
    assert audit.read_events()[0]["event"] == "approved"


def test_edit_and_send_marks_replied_edited(monkeypatch):
    monkeypatch.setattr(
        llm, "classify",
        lambda text: llm.LLMResult(ok=True, parsed={"category": "leasing_inquiry", "urgency": "low", "confidence": 0.9}),
    )
    monkeypatch.setattr(llm, "draft_reply", lambda *a, **k: llm.LLMResult(ok=True, content="Original draft."))
    iid = _make_inquiry()
    pipeline.process_new_inquiry(iid)

    pipeline.edit_and_send(iid, "A rewritten, better reply.")
    row = get_inquiry(iid)
    assert row["status"] == "replied"
    assert row["final_text"] == "A rewritten, better reply."
    assert row["reply_kind"] == "edited"


def test_edit_and_send_on_needs_human_is_tagged_manual(monkeypatch):
    monkeypatch.setattr(llm, "classify", lambda text: llm.LLMResult(ok=False, error="down"))
    iid = _make_inquiry()
    pipeline.process_new_inquiry(iid)  # -> needs_human

    pipeline.edit_and_send(iid, "Manual reply from the owner.")
    row = get_inquiry(iid)
    assert row["status"] == "replied"
    assert row["reply_kind"] == "manual"


def test_reject_marks_rejected(monkeypatch):
    monkeypatch.setattr(
        llm, "classify",
        lambda text: llm.LLMResult(ok=True, parsed={"category": "maintenance_request", "urgency": "low", "confidence": 0.9}),
    )
    monkeypatch.setattr(llm, "draft_reply", lambda *a, **k: llm.LLMResult(ok=True, content="Draft."))
    iid = _make_inquiry()
    pipeline.process_new_inquiry(iid)

    pipeline.reject(iid, reason="wrong info")
    row = get_inquiry(iid)
    assert row["status"] == "rejected"
    assert audit.read_events()[0]["details"]["reason"] == "wrong info"


def test_time_saved_counts_only_ai_assisted_replies():
    rows = [
        {"status": "replied", "reply_kind": "approved"},
        {"status": "replied", "reply_kind": "edited"},
        {"status": "replied", "reply_kind": "manual"},
        {"status": "drafted", "reply_kind": None},
    ]
    # 2 assisted replies * (12 - 2) minutes each = 20
    assert pipeline.time_saved_minutes(rows) == 20
