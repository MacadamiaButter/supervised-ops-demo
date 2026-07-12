"""Escalation rule: confidence < 0.7, OR category=complaint + urgency=high."""

from app.pipeline import should_escalate


def test_low_confidence_escalates_regardless_of_category():
    assert should_escalate("maintenance_request", "low", 0.65) is True


def test_confidence_at_floor_does_not_escalate():
    # floor is a strict "<" -- exactly 0.7 should pass through
    assert should_escalate("leasing_inquiry", "low", 0.70) is False


def test_confidence_just_below_floor_escalates():
    assert should_escalate("leasing_inquiry", "low", 0.699) is True


def test_high_urgency_complaint_escalates_even_with_high_confidence():
    assert should_escalate("complaint", "high", 0.95) is True


def test_complaint_with_low_urgency_does_not_escalate():
    assert should_escalate("complaint", "low", 0.95) is False


def test_high_urgency_non_complaint_does_not_escalate():
    assert should_escalate("maintenance_request", "high", 0.95) is False


def test_high_confidence_non_complaint_low_urgency_clean_path():
    assert should_escalate("vendor", "med", 0.88) is False
