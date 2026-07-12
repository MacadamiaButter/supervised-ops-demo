"""Append-only audit trail.

Design notes
------------
Every meaningful event in the pipeline is appended as one JSON line --
never rewritten, never deleted. This is the core evidence for the
"supervision, not autopilot" pitch: a prospective client should be able
to open this file (or the dashboard panel that renders it) and see
exactly which actions were taken by the AI and which required an
explicit human click. Event types are deliberately restricted to a
fixed vocabulary so the audit trail stays easy to reason about:

    received, classified, drafted, escalated,
    approved, edited, rejected, reminder_fired

No secrets (API keys, bearer tokens) are ever included in an audit
entry -- only lead ids, categories, and short human-readable summaries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import AUDIT_LOG_PATH
from app.db import now_iso

EVENT_TYPES = {
    "received",
    "classified",
    "drafted",
    "escalated",
    "approved",
    "edited",
    "rejected",
    "reminder_fired",
}


def log_event(event: str, inquiry_id: int | None, **details: Any) -> dict:
    if event not in EVENT_TYPES:
        raise ValueError(f"unknown audit event type: {event!r}")
    entry = {
        "ts": now_iso(),
        "event": event,
        "inquiry_id": inquiry_id,
        "details": details,
    }
    Path(AUDIT_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_events(limit: int | None = None, reverse: bool = True) -> list[dict]:
    """Read the audit log. Most-recent-first by default."""
    path = Path(AUDIT_LOG_PATH)
    if not path.exists():
        return []
    events = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if reverse:
        events.reverse()
    if limit is not None:
        events = events[:limit]
    return events


def count_events() -> int:
    path = Path(AUDIT_LOG_PATH)
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def reset_log() -> None:
    """Truncate the audit log -- used by bin/demo-reset."""
    path = Path(AUDIT_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
