"""Central configuration for the Bluejay demo app.

Design notes
------------
Everything that would differ between "demo laptop" and "real deployment"
lives here as a constant with a comment explaining the production value.
Nothing in this file is a secret -- the LLM bearer key is read from disk
at call time by app.llm and is never stored in a module-level constant,
logged, or printed, so it can never leak into a stack trace or an audit
log line.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
AUDIT_LOG_PATH = DATA_DIR / "audit.jsonl"
KB_DIR = DATA_DIR / "kb"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# --- LLM brain (any OpenAI-compatible endpoint) -------------------------

# Works with any OpenAI-compatible chat-completions endpoint: a local
# llama.cpp / Ollama / vLLM server, or a hosted API. Configure via env
# vars; sane local-first defaults if unset.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8080/v1")
LLM_URL = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
LLM_MODEL = os.environ.get("LLM_MODEL", "your-model")

# Optional: path to a file containing a bearer API key, read fresh from
# disk on every call (see read_llm_api_key below). If unset, no
# Authorization header is sent -- fine for a local server with no auth.
_LLM_API_KEY_FILE = os.environ.get("LLM_API_KEY_FILE")
LLM_API_KEY_PATH = Path(_LLM_API_KEY_FILE).expanduser() if _LLM_API_KEY_FILE else None

# httpx clients used for LLM calls are constructed with trust_env=False --
# see app/llm.py. This avoids inherited proxy env vars (HTTPS_PROXY /
# ALL_PROXY etc., commonly set in interactive shells for unrelated
# purposes) silently breaking calls to a local API endpoint.
LLM_TRUST_ENV = False
LLM_TIMEOUT_SECONDS = 60.0

# --- Escalation rule ---------------------------------------------------

# Below this confidence, or any high-urgency complaint, the lead is routed
# straight to a human -- no auto-draft is generated at all.
ESCALATION_CONFIDENCE_FLOOR = 0.7
ESCALATION_CATEGORY = "complaint"
ESCALATION_URGENCY = "high"

# --- Follow-up reminder timing ----------------------------------------

# Production default: 4 hours. For the sales recording we want the
# reminder to actually fire on camera, so DEMO_MODE (on by default in this
# repo, since its only purpose is being demoed) shortens the interval to
# 60 seconds. Set DEMO_MODE=0 in the environment to see the real
# production timing.
DEMO_MODE = os.environ.get("DEMO_MODE", "1") != "0"
FOLLOWUP_INTERVAL_SECONDS = int(
    os.environ.get("FOLLOWUP_INTERVAL_SECONDS", "60" if DEMO_MODE else str(4 * 3600))
)

# --- "Time saved" counter assumptions ----------------------------------

# Purely illustrative for the sales demo: a human drafting a reply from
# scratch takes about this long; reviewing/editing an AI draft takes about
# this long. The difference is what the dashboard counts as "time saved".
MANUAL_DRAFT_MINUTES = 12
AI_ASSISTED_REVIEW_MINUTES = 2

# --- Server bind -------------------------------------------------------

HOST = "127.0.0.1"
PORT = 8300


def read_llm_api_key() -> str | None:
    """Read the bearer key from disk at call time, if LLM_API_KEY_FILE is
    configured.

    Returns None (never raises) if no key file is configured or it can't
    be read, so the app can either send an unauthenticated request (no
    key file configured -- the common local-server case) or fail soft
    into "AI unavailable -- manual mode" (key file configured but
    missing/unreadable) rather than crashing. The key is intentionally
    never assigned to a module-level constant, logged, or included in any
    exception message.
    """
    if LLM_API_KEY_PATH is None:
        return None
    try:
        return LLM_API_KEY_PATH.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
