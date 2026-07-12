"""Orchestration: the inquiry lifecycle, escalation rule, and stats.

This module has no LLM-network code and no web-framework code in it on
purpose -- it's the part that's actually worth unit testing without a
live brain. app/llm.py is injected as a module reference so tests can
monkeypatch app.llm.classify / app.llm.draft_reply.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app import audit, fixtures, kb, llm
from app.config import (
    AI_ASSISTED_REVIEW_MINUTES,
    ESCALATION_CATEGORY,
    ESCALATION_CONFIDENCE_FLOOR,
    ESCALATION_URGENCY,
    FOLLOWUP_INTERVAL_SECONDS,
    MANUAL_DRAFT_MINUTES,
)
from app.db import get_inquiry, list_active_awaiting, now_iso, update_inquiry

TERMINAL_STATUSES = {"replied"}


def should_escalate(category: str, urgency: str, confidence: float) -> bool:
    """The one escalation rule the whole demo hinges on.

    Low classification confidence, OR a high-urgency complaint, routes a
    lead straight to a human with no auto-draft -- see README/DEMO-SCRIPT
    for why this is the point of the product, not an edge case.
    """
    if confidence < ESCALATION_CONFIDENCE_FLOOR:
        return True
    if category == ESCALATION_CATEGORY and urgency == ESCALATION_URGENCY:
        return True
    return False


def _parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def seconds_since(ts: str) -> float:
    return (datetime.now(timezone.utc) - _parse_ts(ts)).total_seconds()


def is_overdue(awaiting_since: str | None, status: str, interval: int | None = None) -> bool:
    """Display-time check: has this lead been sitting untouched longer
    than the follow-up interval? Independent of whether a reminder has
    already fired -- used to keep a lead in the "needs follow-up" queue
    (and its badge visible) for as long as it stays unresolved, not just
    for the instant it crosses the threshold."""
    if status in TERMINAL_STATUSES:
        return False
    if not awaiting_since:
        return False
    window = FOLLOWUP_INTERVAL_SECONDS if interval is None else interval
    return seconds_since(awaiting_since) >= window


def is_followup_due(awaiting_since: str | None, status: str, followup_fired: int, interval: int | None = None) -> bool:
    """Scan-time check: should we fire a NEW reminder event right now?
    Same as is_overdue, but additionally guarded so a reminder is only
    ever logged once per awaiting period (no audit-log spam on every
    poll)."""
    if followup_fired:
        return False
    return is_overdue(awaiting_since, status, interval)


def process_new_inquiry(inquiry_id: int, canned: bool = False) -> None:
    """Run classification (and, unless escalated, drafting) for a
    freshly-created inquiry. Called synchronously right after intake so
    the demo shows the whole chain in one action.

    canned=True swaps the two real LLM calls (classify/draft_reply) for
    the fixed responses in app.fixtures -- used only by the self-running
    tour (?tour=1&canned=1) and bin/record-demo, so a recorded take has
    deterministic timing and text instead of depending on the live brain.
    Everything else (escalation rule, KB grounding, audit logging) runs
    exactly as it would for a real inquiry."""
    row = get_inquiry(inquiry_id)
    if row is None:
        return
    audit.log_event("received", inquiry_id, customer_name=row["customer_name"], channel=row["channel"])

    result = fixtures.canned_classify() if canned else llm.classify(row["raw_text"])
    if not result.ok or result.parsed is None:
        # Fail-soft: brain unavailable -> treat as needing a human, but be
        # explicit in the audit trail about *why* rather than pretending
        # this was a confidence-based escalation.
        update_inquiry(
            inquiry_id,
            status="needs_human",
            awaiting_since=now_iso(),
        )
        audit.log_event("escalated", inquiry_id, reason="ai_unavailable", detail=result.error or "unknown error")
        return

    category = result.parsed["category"]
    urgency = result.parsed["urgency"]
    confidence = result.parsed["confidence"]
    update_inquiry(inquiry_id, category=category, urgency=urgency, confidence=confidence)
    audit.log_event("classified", inquiry_id, category=category, urgency=urgency, confidence=confidence)

    if should_escalate(category, urgency, confidence):
        update_inquiry(inquiry_id, status="needs_human", awaiting_since=now_iso())
        reason = "low_confidence" if confidence < ESCALATION_CONFIDENCE_FLOOR else "high_urgency_complaint"
        audit.log_event("escalated", inquiry_id, reason=reason, confidence=confidence, category=category, urgency=urgency)
        return

    kb_hits = kb.search(row["raw_text"], top_k=2)
    kb_context = "\n\n".join(f"{h['title']}: {h['snippet']}" for h in kb_hits)
    draft_result = (
        fixtures.canned_draft()
        if canned
        else llm.draft_reply(row["raw_text"], category, urgency, kb_context)
    )
    if not draft_result.ok or not draft_result.content:
        update_inquiry(inquiry_id, status="needs_human", awaiting_since=now_iso(), kb_context=kb_context)
        audit.log_event("escalated", inquiry_id, reason="ai_unavailable", detail=draft_result.error or "unknown error")
        return

    update_inquiry(
        inquiry_id,
        status="drafted",
        draft_text=draft_result.content,
        kb_context=kb_context,
        awaiting_since=now_iso(),
    )
    audit.log_event("drafted", inquiry_id, category=category, kb_sources=[h["slug"] for h in kb_hits])


def approve(inquiry_id: int) -> None:
    row = get_inquiry(inquiry_id)
    if row is None:
        return
    update_inquiry(
        inquiry_id,
        status="replied",
        final_text=row["draft_text"],
        reply_kind="approved",
        replied_at=now_iso(),
    )
    audit.log_event("approved", inquiry_id)


def edit_and_send(inquiry_id: int, final_text: str) -> None:
    row = get_inquiry(inquiry_id)
    if row is None:
        return
    was_manual = row["status"] == "needs_human"
    update_inquiry(
        inquiry_id,
        status="replied",
        final_text=final_text,
        reply_kind="manual" if was_manual else "edited",
        replied_at=now_iso(),
    )
    audit.log_event("edited", inquiry_id, manual_reply=was_manual)


def reject(inquiry_id: int, reason: str = "") -> None:
    update_inquiry(inquiry_id, status="rejected", awaiting_since=now_iso())
    audit.log_event("rejected", inquiry_id, reason=reason)


def scan_followups() -> list[int]:
    """Check all active leads; fire (and audit-log) a reminder for any
    that have crossed the follow-up interval untouched. Returns the ids
    that fired this call."""
    fired = []
    for row in list_active_awaiting():
        if is_followup_due(row["awaiting_since"], row["status"], row["followup_fired"]):
            update_inquiry(row["id"], followup_fired=1)
            audit.log_event(
                "reminder_fired",
                row["id"],
                status=row["status"],
                seconds_waiting=int(seconds_since(row["awaiting_since"])) if row["awaiting_since"] else None,
            )
            fired.append(row["id"])
    return fired


def time_saved_minutes(rows) -> int:
    """Very simple illustrative metric: every AI-assisted reply (approved
    or edited, i.e. not a from-scratch manual reply) saves the difference
    between a from-scratch draft and an AI-draft review."""
    assisted = sum(1 for r in rows if r["status"] == "replied" and r["reply_kind"] in ("approved", "edited"))
    return assisted * (MANUAL_DRAFT_MINUTES - AI_ASSISTED_REVIEW_MINUTES)


def avg_response_seconds(rows) -> float | None:
    deltas = []
    for r in rows:
        if r["status"] == "replied" and r["received_at"] and r["replied_at"]:
            deltas.append((_parse_ts(r["replied_at"]) - _parse_ts(r["received_at"])).total_seconds())
    if not deltas:
        return None
    return sum(deltas) / len(deltas)
