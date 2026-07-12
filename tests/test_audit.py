"""Append-only JSONL audit trail."""

import pytest

from app import audit


def test_log_event_appends_and_is_readable():
    audit.log_event("received", 1, customer_name="Ada")
    events = audit.read_events()
    assert len(events) == 1
    assert events[0]["event"] == "received"
    assert events[0]["inquiry_id"] == 1
    assert events[0]["details"]["customer_name"] == "Ada"


def test_unknown_event_type_rejected():
    with pytest.raises(ValueError):
        audit.log_event("not_a_real_event", 1)


def test_read_events_most_recent_first_by_default():
    audit.log_event("received", 1)
    audit.log_event("classified", 1, category="vendor")
    events = audit.read_events()
    assert events[0]["event"] == "classified"
    assert events[1]["event"] == "received"


def test_read_events_limit():
    for i in range(5):
        audit.log_event("received", i)
    assert len(audit.read_events(limit=2)) == 2


def test_count_events():
    assert audit.count_events() == 0
    audit.log_event("received", 1)
    audit.log_event("drafted", 1)
    assert audit.count_events() == 2


def test_reset_log_truncates():
    audit.log_event("received", 1)
    audit.reset_log()
    assert audit.count_events() == 0
