"""SQLite storage layer.

Design notes
------------
This is a small demo, so we use the stdlib sqlite3 module directly rather
than an ORM -- one table, a handful of helper functions, all SQL kept in
one place so it is easy to audit. Every write that changes what a
customer will see (draft, approve, edit, reject) is paired with an
append-only audit-log entry written by app.audit -- the DB row is the
"current state", the JSONL log is the "how we got here" trail that the
dashboard shows off as the audit trail selling point.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS inquiries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at     TEXT NOT NULL,
    customer_name   TEXT NOT NULL,
    customer_contact TEXT NOT NULL,
    channel         TEXT NOT NULL DEFAULT 'webform',
    raw_text        TEXT NOT NULL,
    category        TEXT,
    urgency         TEXT,
    confidence      REAL,
    status          TEXT NOT NULL DEFAULT 'new',
    draft_text      TEXT,
    final_text      TEXT,
    reply_kind      TEXT,
    kb_context      TEXT,
    awaiting_since  TEXT,
    replied_at      TEXT,
    followup_fired  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def reset_db() -> None:
    """Drop and recreate the schema -- used by bin/demo-reset."""
    with get_conn() as conn:
        conn.executescript("DROP TABLE IF EXISTS inquiries;")
        conn.executescript(SCHEMA)


def create_inquiry(
    *,
    customer_name: str,
    customer_contact: str,
    channel: str,
    raw_text: str,
    received_at: str | None = None,
) -> int:
    ts = received_at or now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO inquiries
                (received_at, customer_name, customer_contact, channel, raw_text,
                 status, created_at)
            VALUES (?, ?, ?, ?, ?, 'new', ?)
            """,
            (ts, customer_name, customer_contact, channel, raw_text, now_iso()),
        )
        return int(cur.lastrowid)


def update_inquiry(inquiry_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [inquiry_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE inquiries SET {cols} WHERE id = ?", values)


def get_inquiry(inquiry_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM inquiries WHERE id = ?", (inquiry_id,)
        ).fetchone()


def list_inquiries(order_by: str = "received_at DESC") -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(f"SELECT * FROM inquiries ORDER BY {order_by}").fetchall()


def list_active_awaiting() -> list[sqlite3.Row]:
    """Leads that are not yet resolved (replied) -- candidates for follow-up."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM inquiries WHERE status != 'replied' ORDER BY awaiting_since ASC"
        ).fetchall()
