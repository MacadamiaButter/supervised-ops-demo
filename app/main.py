"""FastAPI app: routes only. All business logic lives in app.pipeline /
app.kb / app.audit / app.db so it can be unit tested without a web
server or a live LLM. Binds to 127.0.0.1:8300 only -- see app.config.

Docstring convention used throughout this package: every module opens
with a short "what this is and why it's shaped this way" note, since
this codebase is also the artifact a prospective client's engineer might
skim to evaluate whether "supervised AI ops" is a real methodology or a
buzzword.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import audit, fixtures, kb, llm, pipeline
from app.config import FOLLOWUP_INTERVAL_SECONDS, HOST, PORT, STATIC_DIR, TEMPLATES_DIR
from app.db import get_inquiry, init_db, list_inquiries, update_inquiry

app = FastAPI(title="Bluejay Property Management -- Supervised AI Ops Demo")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

CATEGORY_LABELS = {
    "maintenance_request": "Maintenance",
    "leasing_inquiry": "Leasing",
    "rent_billing": "Rent & Billing",
    "complaint": "Complaint",
    "vendor": "Vendor",
    "other": "Other",
}
STATUS_LABELS = {
    "new": "New",
    "needs_human": "Needs Human",
    "drafted": "Awaiting Approval",
    "replied": "Replied",
    "rejected": "Rejected -- Needs Manual Reply",
}


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["category_label"] = CATEGORY_LABELS.get(d.get("category"), d.get("category") or "-")
    d["status_label"] = STATUS_LABELS.get(d["status"], d["status"])
    d["followup_due"] = pipeline.is_overdue(d.get("awaiting_since"), d["status"])
    return d


def _dashboard_context(request: Request) -> dict:
    pipeline.scan_followups()  # fire any reminders due right now
    rows = [_row_to_dict(r) for r in list_inquiries()]

    needs_human = [r for r in rows if r["status"] == "needs_human"]
    awaiting_approval = [r for r in rows if r["status"] == "drafted"]
    needs_followup = [r for r in rows if r["followup_due"] or (r["status"] == "rejected")]
    replied = [r for r in rows if r["status"] == "replied"]

    today = datetime.now(timezone.utc).date().isoformat()
    replied_today = [r for r in replied if (r.get("replied_at") or "").startswith(today)]

    status_counts = {}
    for r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    category_counts = {}
    for r in rows:
        if r.get("category"):
            category_counts[r["category"]] = category_counts.get(r["category"], 0) + 1

    brain = llm.check_brain_status()

    avg_secs = pipeline.avg_response_seconds(rows)
    avg_response_label = "n/a"
    if avg_secs is not None:
        if avg_secs < 3600:
            avg_response_label = f"{avg_secs / 60:.0f} min"
        else:
            avg_response_label = f"{avg_secs / 3600:.1f} hr"

    return {
        "request": request,
        "rows": rows,
        "needs_human": needs_human,
        "awaiting_approval": awaiting_approval,
        "needs_followup": needs_followup,
        "replied_today_count": len(replied_today),
        "total_count": len(rows),
        "status_counts": status_counts,
        "category_counts": category_counts,
        "category_labels": CATEGORY_LABELS,
        "time_saved_minutes": pipeline.time_saved_minutes(rows),
        "avg_response_label": avg_response_label,
        "brain_ok": brain.ok,
        "brain_error": brain.error,
        "followup_interval_seconds": FOLLOWUP_INTERVAL_SECONDS,
        "audit_events": audit.read_events(limit=40),
        "audit_total": audit.count_events(),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", _dashboard_context(request))


@app.get("/tour")
def tour_redirect(canned: str | None = None):
    """Convenience alias for the self-running tour -- static/tour.js is
    activated by the ?tour=1 query param on the dashboard route, this
    just saves typing it. /tour == /?tour=1, /tour?canned=1 ==
    /?tour=1&canned=1."""
    qs = "tour=1"
    if canned is not None:
        qs += f"&canned={canned}"
    return RedirectResponse(url=f"/?{qs}")


@app.get("/partials/leads", response_class=HTMLResponse)
def partial_leads(request: Request):
    return templates.TemplateResponse(request, "partials/leads_and_stats.html", _dashboard_context(request))


@app.get("/inquiry/{inquiry_id}", response_class=HTMLResponse)
def inquiry_detail(request: Request, inquiry_id: int):
    row = get_inquiry(inquiry_id)
    if row is None:
        return HTMLResponse("<p>Not found.</p>", status_code=404)
    d = _row_to_dict(row)
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"lead": d, "category_labels": CATEGORY_LABELS},
    )


@app.post("/inquiry/{inquiry_id}/approve")
def api_approve(inquiry_id: int):
    pipeline.approve(inquiry_id)
    return JSONResponse({"ok": True})


@app.post("/inquiry/{inquiry_id}/edit")
def api_edit(inquiry_id: int, final_text: str = Form(...)):
    pipeline.edit_and_send(inquiry_id, final_text)
    return JSONResponse({"ok": True})


@app.post("/inquiry/{inquiry_id}/reject")
def api_reject(inquiry_id: int, reason: str = Form("")):
    pipeline.reject(inquiry_id, reason)
    return JSONResponse({"ok": True})


@app.post("/api/inquiries")
async def api_create_inquiry(request: Request):
    """Used by bin/demo-inject (and static/tour.js) to post a new inquiry
    live during a recording. Runs classification (and drafting, unless
    escalated) synchronously against the real brain -- this can take a
    few seconds up to ~40s depending on load.

    An optional "canned": true field skips the real brain and uses the
    fixed responses in app.fixtures instead (see app.pipeline.
    process_new_inquiry) -- only the tour engine's ?canned=1 mode and
    bin/record-demo ever set this."""
    payload = await request.json()
    customer_name = payload.get("customer_name", "New Inquiry")
    customer_contact = payload.get("customer_contact", "unknown@example.com")
    channel = payload.get("channel", "webform")
    raw_text = payload["raw_text"]
    canned = bool(payload.get("canned", False))

    from app.db import create_inquiry

    inquiry_id = create_inquiry(
        customer_name=customer_name,
        customer_contact=customer_contact,
        channel=channel,
        raw_text=raw_text,
    )
    pipeline.process_new_inquiry(inquiry_id, canned=canned)
    row = get_inquiry(inquiry_id)
    return JSONResponse(_row_to_dict(row))


@app.get("/api/followups/scan")
def api_scan_followups():
    fired = pipeline.scan_followups()
    return JSONResponse({"fired": fired})


@app.get("/kb", response_class=HTMLResponse)
def kb_page(request: Request, q: str = ""):
    results = kb.search(q, top_k=10) if q else []
    docs = kb.all_docs()
    return templates.TemplateResponse(
        request, "kb.html", {"q": q, "results": results, "docs": docs}
    )


@app.get("/api/kb/search")
def api_kb_search(q: str = ""):
    return JSONResponse({"results": kb.search(q, top_k=5)})


@app.post("/api/summary")
def api_generate_summary(canned: bool = False):
    """canned=1 skips the real brain and returns the fixed summary in
    app.fixtures -- same reasoning as api_create_inquiry's canned flag."""
    rows = [_row_to_dict(r) for r in list_inquiries()]
    slim = [
        {
            "category": r.get("category"),
            "urgency": r.get("urgency"),
            "status": r["status"],
            "received_at": r["received_at"],
        }
        for r in rows
    ]
    result = fixtures.canned_summary() if canned else llm.generate_owner_summary(json.dumps(slim))
    if not result.ok:
        return JSONResponse({"ok": False, "error": result.error}, status_code=503)
    return JSONResponse({"ok": True, "summary": result.content})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
