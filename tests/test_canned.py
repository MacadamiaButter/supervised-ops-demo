"""The canned/fixture path (?canned=1 -- used by the self-running tour,
static/tour.js, and bin/record-demo for deterministic recordings) must
never touch the real LLM calls, and must produce the exact same shape of
state/audit trail a live run would."""

import json

from app import audit, fixtures, llm, pipeline
from app import main as main_module
from app.db import create_inquiry, get_inquiry


def _make_inquiry(text="My kitchen faucet has been dripping for two days."):
    return create_inquiry(
        customer_name="Taylor Brooks",
        customer_contact="taylor.brooks@example.com",
        channel="webform",
        raw_text=text,
    )


def _boom(*a, **k):
    raise AssertionError("canned=True must never call the real LLM")


def test_canned_path_never_calls_the_real_llm(monkeypatch):
    monkeypatch.setattr(llm, "classify", _boom)
    monkeypatch.setattr(llm, "draft_reply", _boom)

    iid = _make_inquiry()
    pipeline.process_new_inquiry(iid, canned=True)

    row = get_inquiry(iid)
    assert row["status"] == "drafted"
    assert row["category"] == fixtures.CANNED_CLASSIFICATION.parsed["category"]
    assert row["urgency"] == fixtures.CANNED_CLASSIFICATION.parsed["urgency"]
    assert row["draft_text"] == fixtures.CANNED_DRAFT.content


def test_canned_path_produces_the_normal_audit_trail(monkeypatch):
    monkeypatch.setattr(llm, "classify", _boom)
    monkeypatch.setattr(llm, "draft_reply", _boom)

    iid = _make_inquiry()
    pipeline.process_new_inquiry(iid, canned=True)

    events = [e["event"] for e in audit.read_events(reverse=False)]
    assert events == ["received", "classified", "drafted"]


def test_canned_defaults_to_false_and_still_uses_the_real_llm(monkeypatch):
    called = {"classify": False}

    def fake_classify(text):
        called["classify"] = True
        return llm.LLMResult(
            ok=True,
            parsed={"category": "maintenance_request", "urgency": "low", "confidence": 0.9},
        )

    monkeypatch.setattr(llm, "classify", fake_classify)
    monkeypatch.setattr(llm, "draft_reply", lambda *a, **k: llm.LLMResult(ok=True, content="real draft"))

    iid = _make_inquiry()
    pipeline.process_new_inquiry(iid)  # canned not passed -> defaults False

    assert called["classify"] is True


def test_summary_canned_flag_skips_the_real_llm(monkeypatch):
    monkeypatch.setattr(main_module.llm, "generate_owner_summary", _boom)

    resp = main_module.api_generate_summary(canned=True)
    data = json.loads(resp.body)

    assert data["ok"] is True
    assert data["summary"] == fixtures.CANNED_SUMMARY.content


def test_summary_default_canned_false_uses_the_real_llm(monkeypatch):
    called = {"summary": False}

    def fake_summary(leads_json):
        called["summary"] = True
        return llm.LLMResult(ok=True, content="real summary")

    monkeypatch.setattr(main_module.llm, "generate_owner_summary", fake_summary)

    resp = main_module.api_generate_summary()  # canned defaults False
    data = json.loads(resp.body)

    assert called["summary"] is True
    assert data["summary"] == "real summary"
