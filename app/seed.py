"""Seed data for a lively-looking first-open dashboard.

Design notes
------------
These 8 inquiries are hand-crafted, not produced by a live LLM call --
running bin/demo-reset should be instant and not depend on the brain
being reachable. Classification/draft text here is what a real run
would plausibly produce; each seed row is paired with matching
audit-log entries so the "full audit trail" panel tells a consistent
story from the very first page load, not just the DB state.

Timestamps are relative to "now" at reset time so response-time and
follow-up-due calculations look realistic regardless of when the demo
is run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import audit
from app.db import create_inquiry, reset_db, update_inquiry


def _ts(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")


def seed_all() -> None:
    reset_db()
    audit.reset_log()

    # 1) Maintenance emergency -> classified -> drafted -> approved (fast, clean path)
    iid = create_inquiry(
        customer_name="Marcus Whitfield",
        customer_contact="marcus.whitfield@example.com",
        channel="webform",
        raw_text="Hi, there's water leaking from the ceiling in my kitchen at Larkspur Unit 4B, "
                 "it's getting worse and there's a puddle forming. Can someone come look today?",
        received_at=_ts(320),
    )
    audit.log_event("received", iid, customer_name="Marcus Whitfield", channel="webform")
    update_inquiry(iid, category="maintenance_request", urgency="high", confidence=0.94)
    audit.log_event("classified", iid, category="maintenance_request", urgency="high", confidence=0.94)
    draft = (
        "Hi Marcus, thanks for flagging this right away -- an active ceiling leak is an "
        "emergency-tier issue for us. I've dispatched our on-call plumbing vendor with a "
        "2-hour response window; you'll get a text with their name and ETA shortly. If the "
        "leak worsens or you lose power near the water, please call the 24/7 emergency line "
        "at (503) 555-0199. -- The Bluejay Team"
    )
    update_inquiry(iid, status="drafted", draft_text=draft, kb_context="Maintenance response SLAs; Emergency contacts", awaiting_since=_ts(319))
    audit.log_event("drafted", iid, category="maintenance_request", kb_sources=["maintenance-sla", "emergency-contacts"])
    update_inquiry(iid, status="replied", final_text=draft, reply_kind="approved", replied_at=_ts(300))
    audit.log_event("approved", iid)

    # 2) Leasing inquiry -> drafted, awaiting approval (not yet overdue)
    iid = create_inquiry(
        customer_name="Priya Nandakumar",
        customer_contact="(971) 555-0118",
        channel="phone-log",
        raw_text="Hello, I saw the 2-bedroom listing at Sable Court online. Is it still available, "
                 "and are cats allowed there? Would love to schedule a tour this week.",
        received_at=_ts(18),
    )
    audit.log_event("received", iid, customer_name="Priya Nandakumar", channel="phone-log")
    update_inquiry(iid, category="leasing_inquiry", urgency="low", confidence=0.88)
    audit.log_event("classified", iid, category="leasing_inquiry", urgency="low", confidence=0.88)
    draft2 = (
        "Hi Priya, thanks for your interest in Sable Court! Cats are welcome there (pet "
        "deposit $300 plus $35/month pet rent, up to 2 pets). I'd be glad to check current "
        "availability and get a tour on the calendar this week -- what days/times generally "
        "work best for you? -- The Bluejay Team"
    )
    update_inquiry(iid, status="drafted", draft_text=draft2, kb_context="Pet policy", awaiting_since=_ts(17))
    audit.log_event("drafted", iid, category="leasing_inquiry", kb_sources=["pet-policy"])

    # 3) Rent/billing question -> drafted, deliberately overdue so a
    #    follow-up reminder is already live the moment the demo opens.
    iid = create_inquiry(
        customer_name="Dana Ferreira",
        customer_contact="dana.ferreira@example.com",
        channel="webform",
        raw_text="I think I was charged a late fee this month but I paid on the 3rd, well "
                 "within the grace period. Can you take a look at my account?",
        received_at=_ts(240),
    )
    audit.log_event("received", iid, customer_name="Dana Ferreira", channel="webform")
    update_inquiry(iid, category="rent_billing", urgency="med", confidence=0.81)
    audit.log_event("classified", iid, category="rent_billing", urgency="med", confidence=0.81)
    draft3 = (
        "Hi Dana, thanks for flagging this -- rent paid on the 3rd is within our 5-day grace "
        "period, so a late fee shouldn't have applied. I've submitted this to get your "
        "account reviewed and the charge corrected if it was applied in error; you'll see an "
        "update on the portal, and I'll follow up personally. -- The Bluejay Team"
    )
    update_inquiry(iid, status="drafted", draft_text=draft3, kb_context="Rent payment & billing", awaiting_since=_ts(235))
    audit.log_event("drafted", iid, category="rent_billing", kb_sources=["rent-payment"])

    # 4) Complaint + high urgency -> hard-rule escalation (the flagship
    #    "supervision catches this even though confidence is high" case)
    iid = create_inquiry(
        customer_name="Robert Chu",
        customer_contact="robert.chu@example.com",
        channel="email",
        raw_text="This is the THIRD time I've called about the noise from unit 12 at 2am. "
                 "Nobody has done anything. This is completely unacceptable and I am looking "
                 "into breaking my lease and contacting a tenant rights attorney.",
        received_at=_ts(95),
    )
    audit.log_event("received", iid, customer_name="Robert Chu", channel="email")
    update_inquiry(iid, category="complaint", urgency="high", confidence=0.86)
    audit.log_event("classified", iid, category="complaint", urgency="high", confidence=0.86)
    update_inquiry(iid, status="needs_human", awaiting_since=_ts(94))
    audit.log_event("escalated", iid, reason="high_urgency_complaint", confidence=0.86, category="complaint", urgency="high")

    # 5) Low-confidence classification -> escalation via the confidence
    #    floor, distinct from the complaint hard-rule above
    iid = create_inquiry(
        customer_name="Unclear Sender",
        customer_contact="tenant-relay-9928@example.com",
        channel="webform",
        raw_text="hey so about the thing with the unit and the guy from before, can u guys "
                 "sort it out or what, its been a min",
        received_at=_ts(50),
    )
    audit.log_event("received", iid, customer_name="Unclear Sender", channel="webform")
    update_inquiry(iid, category="other", urgency="low", confidence=0.52)
    audit.log_event("classified", iid, category="other", urgency="low", confidence=0.52)
    update_inquiry(iid, status="needs_human", awaiting_since=_ts(49))
    audit.log_event("escalated", iid, reason="low_confidence", confidence=0.52, category="other", urgency="low")

    # 6) Leasing inquiry -> owner edited the draft before sending
    iid = create_inquiry(
        customer_name="Sofia Marchetti",
        customer_contact="sofia.m@example.com",
        channel="webform",
        raw_text="What's the process for renewing my lease? It's up in a couple months and "
                 "I'd like to stay but maybe on a shorter term.",
        received_at=_ts(600),
    )
    audit.log_event("received", iid, customer_name="Sofia Marchetti", channel="webform")
    update_inquiry(iid, category="leasing_inquiry", urgency="low", confidence=0.91)
    audit.log_event("classified", iid, category="leasing_inquiry", urgency="low", confidence=0.91)
    draft6 = (
        "Hi Sofia, happy to help! Renewal offers go out 90 days before lease end with 60 "
        "days to respond, and you can request a shorter 6 or 9 month term (+$50/mo admin "
        "fee). -- The Bluejay Team"
    )
    final6 = (
        "Hi Sofia, happy to help! Your renewal offer will go out automatically about 90 "
        "days before your lease ends, and you'll have 60 days to respond. You're welcome to "
        "request a shorter 6- or 9-month term (there's a small +$50/month admin fee for "
        "short terms). I've also noted your interest in staying so we can flag it internally "
        "-- talk soon! -- The Bluejay Team"
    )
    update_inquiry(iid, status="drafted", draft_text=draft6, kb_context="Lease renewal process", awaiting_since=_ts(598))
    audit.log_event("drafted", iid, category="leasing_inquiry", kb_sources=["lease-renewal"])
    update_inquiry(iid, status="replied", final_text=final6, reply_kind="edited", replied_at=_ts(560))
    audit.log_event("edited", iid, manual_reply=False)

    # 7) Maintenance draft rejected by the owner (draft had the wrong SLA
    #    tier) -- still needs a manual reply, overdue for follow-up
    iid = create_inquiry(
        customer_name="Elena Vasquez",
        customer_contact="elena.vasquez@example.com",
        channel="webform",
        raw_text="My dishwasher stopped draining properly, water pools at the bottom after "
                 "each cycle. Not urgent but would like it looked at.",
        received_at=_ts(180),
    )
    audit.log_event("received", iid, customer_name="Elena Vasquez", channel="webform")
    update_inquiry(iid, category="maintenance_request", urgency="low", confidence=0.89)
    audit.log_event("classified", iid, category="maintenance_request", urgency="low", confidence=0.89)
    draft7 = (
        "Hi Elena, sorry about the dishwasher! I've flagged this as an emergency repair and "
        "a vendor will be dispatched within 2 hours. -- The Bluejay Team"
    )
    update_inquiry(iid, status="drafted", draft_text=draft7, kb_context="Maintenance response SLAs", awaiting_since=_ts(178))
    audit.log_event("drafted", iid, category="maintenance_request", kb_sources=["maintenance-sla"])
    update_inquiry(iid, status="rejected", awaiting_since=_ts(175))
    audit.log_event("rejected", iid, reason="wrong SLA tier quoted -- this is routine (3-5 business days), not emergency")

    # 8) Complaint, low urgency -> not a hard-rule escalation, clean
    #    approve path (shows category alone doesn't trigger escalation)
    iid = create_inquiry(
        customer_name="Gary Holt",
        customer_contact="gary.holt@example.com",
        channel="email",
        raw_text="The community room booking calendar on the portal is confusing, I booked "
                 "the wrong weekend by accident. Minor gripe but wanted to mention it.",
        received_at=_ts(420),
    )
    audit.log_event("received", iid, customer_name="Gary Holt", channel="email")
    update_inquiry(iid, category="complaint", urgency="low", confidence=0.9)
    audit.log_event("classified", iid, category="complaint", urgency="low", confidence=0.9)
    draft8 = (
        "Hi Gary, thanks for the feedback -- sorry the booking calendar tripped you up! I've "
        "gone ahead and corrected your community room reservation, and I'm passing your note "
        "along to see if we can make the calendar clearer. -- The Bluejay Team"
    )
    update_inquiry(iid, status="drafted", draft_text=draft8, kb_context="Amenities & common areas", awaiting_since=_ts(419))
    audit.log_event("drafted", iid, category="complaint", kb_sources=["amenities"])
    update_inquiry(iid, status="replied", final_text=draft8, reply_kind="approved", replied_at=_ts(400))
    audit.log_event("approved", iid)


if __name__ == "__main__":
    seed_all()
    print("Seeded 8 demo inquiries.")
