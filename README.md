# Bluejay Property Management -- Supervised AI Operations Demo

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A small, self-contained demonstration of a **supervised AI operations**
pattern for an SMB: an LLM triages inbound customer messages and drafts
replies, but a human explicitly approves, edits, or rejects every reply
before it counts as sent. Nothing goes out the door on autopilot. The AI
does the first 80% of the work (reading, categorizing, drafting)
instantly and consistently; a human does the last 20% (a 10-second
glance and a click) that actually matters for tone, accuracy, and
liability; and every action -- AI or human -- is logged to an append-only
audit trail the owner can open at any time. The one thing the AI is
never allowed to do is decide, alone, that a message doesn't need a
human at all, when it's a high-urgency complaint or when it isn't
confident in its own read.

Bluejay Property Management is a fictional company invented for this
demo.

**Watch the 2-minute demo video:** https://localfirstlab.org/demo.html

## Why supervision, not autopilot

The pitch to an SMB owner is never "let the AI run your inbox." It's:
the AI does the first pass, a human stays the last checkpoint before
anything reaches a customer, and there's a real record of who did what.
That's the whole idea, and this repo is the smallest thing that shows it
end to end -- not a product, a demonstration of the pattern.

## Architecture sketch

```
inbound inquiry (webform/phone-log/email -- simulated here)
        |
        v
  POST /api/inquiries  ->  app/pipeline.process_new_inquiry()
        |
        |-- app/llm.classify()          (json_schema structured output)
        |       category / urgency / confidence
        |
        |-- app/pipeline.should_escalate()
        |       confidence < 0.7  OR  complaint+high  -> status=needs_human, STOP
        |
        |-- app/kb.search()              (BM25-ish, data/kb/*.md)
        |-- app/llm.draft_reply()        (grounded with top KB snippets)
        |       -> status=drafted, awaiting owner action
        v
  owner reviews in the dashboard (app/main.py + templates/detail.html)
        |
        |-- approve  -> status=replied, reply_kind=approved
        |-- edit     -> status=replied, reply_kind=edited (or manual, if it
        |                started as needs_human/rejected)
        |-- reject   -> status=rejected, still needs a manual reply
        v
  every step above is appended to data/audit.jsonl (app/audit.py) --
  never rewritten, rendered live in the dashboard's audit-trail panel
```

Storage is one SQLite table (`app/db.py`) for current lead state, plus an
append-only JSONL file for the audit trail -- deliberately two different
mechanisms, because "what is true right now" and "how did we get here"
are different questions, and conflating them (e.g. UPDATE-in-place with
no history) is exactly what makes an AI pipeline hard for an owner to
trust.

Follow-up reminders (`app/pipeline.scan_followups`) and the "time saved"
counter are both simple, explainable, on-purpose-not-clever
calculations -- see the docstrings in `app/config.py` and
`app/pipeline.py` for the exact rules.

### Stack

- Python 3 + FastAPI/uvicorn, server-rendered Jinja2 templates, one
  hand-written CSS file, small vanilla-JS fetch helpers (`static/app.js`)
  for the live-polling dashboard and detail-panel interactions. No
  frontend framework, no build step, no CDN dependency -- it runs fully
  offline aside from the LLM call itself.
- SQLite for lead state; append-only JSONL for the audit trail.
- A dependency-free BM25-ish keyword search (`app/kb.py`) over 10 seeded
  markdown knowledge-base snippets -- no vector DB / embedding service,
  so the whole demo is self-contained.
- LLM calls go to any OpenAI-compatible chat-completions endpoint
  (`app/llm.py`), configured entirely through environment variables (see
  below) -- a local llama.cpp/Ollama/vLLM server or a hosted API both
  work unmodified. Classification uses `response_format: json_schema` so
  category/urgency/confidence come back machine-parseable; drafting and
  the owner summary are plain free-text completions. The bearer key (if
  any) is read from disk at call time and never logged, printed, or
  hard-coded.

### A gotcha worth knowing about

Interactive shells sometimes carry `HTTPS_PROXY`/`ALL_PROXY` env vars
for unrelated purposes (a VPN, a corporate proxy, a privacy tunnel). A
proxy like that usually can't reach a local API endpoint, so every
httpx client used for LLM calls here is constructed with
`trust_env=False` -- this avoids inherited proxy env vars breaking local
API calls. If you ever see "AI unavailable" on a box where the LLM
server is actually up, check for a stray proxy env var first.

## Quickstart

```
python3 -m venv venv
./venv/bin/pip install -r requirements.txt      # + requirements-dev.txt for tests
./venv/bin/python -m app.seed                   # or: bin/demo-reset

export LLM_BASE_URL=http://localhost:8080/v1    # any OpenAI-compatible server
export LLM_MODEL=your-model
# export LLM_API_KEY_FILE=~/.config/some-service/api-key   # optional; omit for no-auth local servers

./venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8300
```

Then open http://127.0.0.1:8300/. The app binds to `127.0.0.1:8300`
only -- it is not meant to be reachable from anywhere else.

### Configuration (environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_BASE_URL` | `http://localhost:8080/v1` | Base URL of an OpenAI-compatible endpoint (llama.cpp, Ollama, vLLM, a hosted API, ...). `/chat/completions` is appended automatically. |
| `LLM_MODEL` | `your-model` | Model name/id sent in each request's `model` field. |
| `LLM_API_KEY_FILE` | unset | Optional path to a file containing a bearer API key. If unset, requests are sent with no `Authorization` header -- fine for local, unauthenticated servers. |
| `DEMO_MODE` | `1` | Shortens the follow-up interval to 60 seconds so a reminder visibly fires quickly. Set to `0` for the real production default (4 hours). |
| `FOLLOWUP_INTERVAL_SECONDS` | derived from `DEMO_MODE` | Override the follow-up window directly. |

No API key value is ever hard-coded anywhere in this codebase -- only
the *path* to an optional key file is configurable, and the key itself
is read from disk at call time (see `app/config.py`, `app/llm.py`).

## Demo helpers

- `bin/demo-reset` -- restores the pristine seeded state (8 hand-crafted
  inquiries across every status/category). Does not call the LLM, so
  it's instant and safe to run right before recording even if the LLM
  server is down.
- `bin/demo-inject "some inquiry text..."` -- posts a brand-new inquiry
  to the running app, so a recording can show one arriving live and
  being classified/drafted by the real LLM in real time (a few seconds
  up to ~40s depending on load).
- `?tour=1` on the dashboard URL runs a self-contained, self-running
  storyboard tour of the whole click-path (add `&canned=1` for
  deterministic fixture responses instead of a live LLM call).
- `bin/record-demo` -- automated video capture of the `?tour=1` tour via
  Playwright + Chromium, converted to H.264 MP4 with ffmpeg. Defaults to
  canned/deterministic mode; `TOUR_MODE=live bin/record-demo` records
  against a real LLM instead. Requires `requirements-dev.txt` plus
  `./venv/bin/playwright install chromium`.

See `DEMO-SCRIPT.md` for a full 2-minute click-path script (written for
recording a screen-capture walkthrough).

## Tests

`tests/` covers the non-LLM logic with the LLM fully mocked: the
escalation rule, follow-up timing, KB search ranking, audit-log
append/read, and the full lead lifecycle (classify -> draft/escalate ->
approve/edit/reject) -- 41 tests, all passing offline, no network calls.

```
./venv/bin/python -m pytest tests/ -q
```

## What production adds

This demo is intentionally the smallest thing that tells the whole
story. A real deployment for a paying client would add:

- **Real intake integrations** -- email (IMAP/webhook), a webform
  endpoint with spam/abuse filtering, and/or SMS, instead of a single
  `POST /api/inquiries` and a CLI injector.
- **Per-client isolated deployment** -- one database, one audit log, one
  KB, one API key per client, not a shared multi-tenant instance;
  probably one small VM or container per client rather than a shared
  service, given how much the "your data never touches anyone else's
  system" story matters to this kind of buyer.
- **Monitoring & alerting** -- uptime/health checks on the LLM endpoint
  and the app itself, an on-call path if the escalation queue backs up,
  error tracking, and a real notification channel (SMS/push/email) for
  needs-human items and follow-up reminders instead of a dashboard badge
  you have to be looking at.
- **A real embedding-backed knowledge base** -- BM25-over-markdown is
  honest and good enough for ~10 snippets; a real client KB (dozens to
  hundreds of policy documents, unit-specific details, past correspondence)
  would want a proper vector index and a re-ranker.
- **Scheduled jobs, not buttons** -- the daily owner summary and the
  follow-up scan are demo buttons/polling here; production would run
  them on a cron/scheduler and push the summary out (email/SMS) rather
  than requiring the owner to open the dashboard.
- **Contractual async support & data-handling terms** -- an SLA for LLM
  downtime / fail-soft behavior, a written data-retention and deletion
  policy, and a support channel for when the AI gets something wrong --
  this is a trust product as much as a software product, and those
  terms need to be as concrete as the code.
- **Authn/authz** -- this demo has no login because it's a single-owner
  local recording; production needs real accounts, role separation (e.g.
  a property manager vs. the owner), and audit entries attributed to a
  specific human, not just "the dashboard."

## License

MIT -- see [LICENSE](LICENSE).

---

Built by [Local First Lab](https://localfirstlab.org) -- hello@localfirstlab.org
