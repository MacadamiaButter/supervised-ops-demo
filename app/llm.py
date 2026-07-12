"""Calls to the LLM brain (any OpenAI-compatible chat-completions endpoint).

Design notes
------------
- The bearer key, if configured (LLM_API_KEY_FILE), is read fresh from
  disk on every call (app.config.read_llm_api_key) and is never logged,
  printed, or embedded in an exception message. If a key file is
  configured but missing/unreadable, or the brain is unreachable, every
  function here returns a structured "unavailable" result rather than
  raising -- the app fails soft into manual mode. If no key file is
  configured, requests are sent without an Authorization header, which
  is the common case for a local, unauthenticated server.
- httpx clients here are constructed with trust_env=False, which avoids
  inherited proxy env vars (HTTPS_PROXY/ALL_PROXY etc., commonly set in
  interactive shells for unrelated purposes) breaking calls to a local
  API endpoint.
- Classification uses response_format json_schema (an OpenAI-compatible
  structured-output feature supported by llama.cpp, vLLM, and others) so
  category, urgency, and confidence come back machine-parseable instead
  of hoping the model's prose parses. Draft generation and the owner
  summary are plain free-text completions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import (
    LLM_API_KEY_PATH,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    LLM_URL,
    read_llm_api_key,
)

CATEGORIES = [
    "maintenance_request",
    "leasing_inquiry",
    "rent_billing",
    "complaint",
    "vendor",
    "other",
]
URGENCIES = ["low", "med", "high"]

CLASSIFICATION_SCHEMA = {
    "name": "inquiry_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "urgency": {"type": "string", "enum": URGENCIES},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["category", "urgency", "confidence"],
        "additionalProperties": False,
    },
}

CLASSIFY_SYSTEM_PROMPT = (
    "You triage inbound customer messages for Bluejay Property Management, "
    "a residential property management company. Classify the message into "
    "exactly one category (maintenance_request, leasing_inquiry, "
    "rent_billing, complaint, vendor, other), pick an urgency (low, med, "
    "high) based on safety/time-sensitivity, and give your confidence in "
    "this classification from 0 to 1. Life-safety issues (gas leak, no "
    "heat in freezing weather, active flooding) are always high urgency. "
    "Respond with ONLY the JSON object, no other text."
)

DRAFT_SYSTEM_PROMPT = (
    "You draft the FIRST-PASS reply to a customer inquiry for Bluejay "
    "Property Management. A human property manager will review, edit, or "
    "reject this draft before anything is sent -- you are producing a "
    "starting point, not a final message. Be warm, concise (under 150 "
    "words), professional, and specific: use the company knowledge-base "
    "context provided if it's relevant, and never invent policy details, "
    "dates, prices, or promises that aren't in the context or the "
    "customer's message. If you're not sure of a fact, say the manager "
    "will confirm it rather than guessing. Sign off as 'The Bluejay Team'."
)

SUMMARY_SYSTEM_PROMPT = (
    "You write a short (4-6 sentence) daily operations summary for the "
    "owner of Bluejay Property Management, based on a JSON list of "
    "today's customer leads. Mention volume, the mix of categories, "
    "anything flagged for human review, and anything still awaiting a "
    "reply. Plain prose, no bullet points, no headers."
)


@dataclass
class LLMResult:
    ok: bool
    content: str | None = None
    parsed: dict | None = None
    error: str | None = None


def _client() -> httpx.Client:
    # trust_env=False is load-bearing -- see module docstring.
    return httpx.Client(trust_env=False, timeout=LLM_TIMEOUT_SECONDS)


def _auth_headers() -> tuple[dict[str, str], str | None]:
    """Build request headers, plus an error string if a key file was
    configured but couldn't be read. No LLM_API_KEY_FILE configured at
    all is not an error -- it just means an unauthenticated request."""
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY_PATH is None:
        return headers, None
    api_key = read_llm_api_key()
    if not api_key:
        return headers, "configured API key file is missing or empty"
    headers["Authorization"] = f"Bearer {api_key}"
    return headers, None


def _post(payload: dict[str, Any]) -> LLMResult:
    headers, error = _auth_headers()
    if error:
        return LLMResult(ok=False, error=error)
    try:
        with _client() as client:
            resp = client.post(LLM_URL, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        return LLMResult(ok=False, error=f"brain unreachable ({type(exc).__name__})")
    if resp.status_code != 200:
        return LLMResult(ok=False, error=f"brain returned HTTP {resp.status_code}")
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        return LLMResult(ok=False, error="malformed brain response")
    return LLMResult(ok=True, content=content)


def classify(text: str) -> LLMResult:
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.1,
        "max_tokens": 200,
        "response_format": {"type": "json_schema", "json_schema": CLASSIFICATION_SCHEMA},
    }
    result = _post(payload)
    if not result.ok or result.content is None:
        return result
    try:
        parsed = json.loads(result.content)
        category = parsed["category"]
        urgency = parsed["urgency"]
        confidence = float(parsed["confidence"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return LLMResult(ok=False, error="brain returned unparseable classification JSON")
    if category not in CATEGORIES or urgency not in URGENCIES:
        return LLMResult(ok=False, error="brain returned an out-of-schema value")
    return LLMResult(ok=True, content=result.content, parsed={
        "category": category, "urgency": urgency, "confidence": confidence,
    })


def draft_reply(text: str, category: str, urgency: str, kb_context: str) -> LLMResult:
    user_msg = f"Customer message:\n{text}\n\nCategory: {category}\nUrgency: {urgency}"
    if kb_context:
        user_msg += f"\n\nRelevant company knowledge base context:\n{kb_context}"
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
        "top_p": 0.8,
        "max_tokens": 600,
    }
    return _post(payload)


def check_brain_status(timeout_seconds: float = 5.0) -> LLMResult:
    """Cheap reachability probe used to drive the "AI unavailable -- manual
    mode" banner. Deliberately max_tokens=1 / temperature=0 so it's fast
    and doesn't burn a real generation slot."""
    headers, error = _auth_headers()
    if error:
        return LLMResult(ok=False, error=error)
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": "ping"}],
        "temperature": 0,
        "max_tokens": 1,
    }
    try:
        with httpx.Client(trust_env=False, timeout=timeout_seconds) as client:
            resp = client.post(LLM_URL, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        return LLMResult(ok=False, error=f"brain unreachable ({type(exc).__name__})")
    if resp.status_code != 200:
        return LLMResult(ok=False, error=f"brain returned HTTP {resp.status_code}")
    return LLMResult(ok=True)


def generate_owner_summary(leads_json: str) -> LLMResult:
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": leads_json},
        ],
        "temperature": 0.5,
        "max_tokens": 350,
    }
    return _post(payload)
