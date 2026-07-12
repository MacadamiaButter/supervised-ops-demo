"""Deterministic stand-ins for app.llm calls -- used ONLY when a caller
explicitly opts in with canned=True/?canned=1.

Design notes
------------
This exists for exactly one reason: bin/record-demo (and static/tour.js's
?tour=1&canned=1 mode) needs a recording take with fixed timing and fixed
on-screen text, so re-running it produces the same video. A live LLM call
takes 5-40s and the model's wording varies run to run -- fine for an
in-person demo, bad for a video asset you want to re-cut deterministically.

These are NEVER used for a real inquiry -- app.pipeline.process_new_inquiry
and app.main.api_generate_summary only reach for them when the caller
passes canned=True, which only the tour engine and bin/record-demo ever
do. The shape of each result matches what app.llm actually returns (see
app.llm.LLMResult) so the rest of the pipeline can't tell the difference.

The classification/draft text below is written to match the seeded
"leaky faucet" example from DEMO-SCRIPT.md and data/kb/maintenance-sla.md
(a dripping faucet is explicitly a "Routine" item there -- 3-5 business
days, not emergency) so the canned run stays consistent with the rest of
the demo's story if someone reads the KB alongside it.
"""

from __future__ import annotations

from app.llm import LLMResult

CANNED_CLASSIFICATION = LLMResult(
    ok=True,
    content='{"category": "maintenance_request", "urgency": "med", "confidence": 0.93}',
    parsed={"category": "maintenance_request", "urgency": "med", "confidence": 0.93},
)

CANNED_DRAFT = LLMResult(
    ok=True,
    content=(
        "Hi Taylor, thanks for letting us know -- a dripping kitchen faucet "
        "is a routine maintenance item, so we'll have a plumbing vendor out "
        "within our standard 3-5 business day window and confirm a time "
        "that works for you by text or portal message. If it starts "
        "leaking heavily or you notice any water pooling, let us know "
        "right away and we'll treat it as urgent instead. -- The Bluejay "
        "Team"
    ),
)

CANNED_SUMMARY = LLMResult(
    ok=True,
    content=(
        "Today brought a steady mix of maintenance, leasing, and "
        "rent/billing messages, plus one high-urgency complaint that was "
        "routed straight to a human under the escalation rule. Most "
        "inquiries were classified and drafted automatically and are "
        "waiting on an approve, edit, or reject click. A couple of leads "
        "are still open past the follow-up window and could use a look."
    ),
)


def canned_classify() -> LLMResult:
    return CANNED_CLASSIFICATION


def canned_draft() -> LLMResult:
    return CANNED_DRAFT


def canned_summary() -> LLMResult:
    return CANNED_SUMMARY
