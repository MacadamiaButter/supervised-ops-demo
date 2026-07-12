"""Follow-up reminder timing -- configurable interval, fires once, but
stays visible in the queue (is_overdue) for as long as it's unresolved."""

from datetime import datetime, timedelta, timezone

from app.pipeline import is_followup_due, is_overdue

INTERVAL = 60


def _ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds")


def test_not_due_before_interval_elapses():
    assert is_followup_due(_ago(10), "drafted", 0, interval=INTERVAL) is False


def test_due_after_interval_elapses():
    assert is_followup_due(_ago(120), "drafted", 0, interval=INTERVAL) is True


def test_not_due_if_already_fired():
    assert is_followup_due(_ago(120), "drafted", 1, interval=INTERVAL) is False


def test_not_due_for_replied_terminal_status():
    assert is_followup_due(_ago(9999), "replied", 0, interval=INTERVAL) is False


def test_not_due_with_no_awaiting_since():
    assert is_followup_due(None, "drafted", 0, interval=INTERVAL) is False


def test_needs_human_leads_are_also_eligible_for_followup():
    assert is_followup_due(_ago(120), "needs_human", 0, interval=INTERVAL) is True


def test_is_overdue_stays_true_after_reminder_already_fired():
    # queue/badge visibility must not disappear just because the
    # one-time audit reminder already fired
    assert is_overdue(_ago(120), "drafted", interval=INTERVAL) is True


def test_is_overdue_false_for_replied():
    assert is_overdue(_ago(9999), "replied", interval=INTERVAL) is False
