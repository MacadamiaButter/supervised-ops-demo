# DEMO-SCRIPT.md -- 2-minute screen recording click-path

Audience: a prospective SMB owner who has never seen the product. Goal:
in two minutes, they should understand (1) the AI does real work, (2)
they are never one AI mistake away from an embarrassing email going out,
and (3) they can see exactly what happened, always.

## Before you hit record

```
cd path/to/supervised-ops-demo
./bin/demo-reset                              # pristine 8-lead seed state
./venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8300
```

Open http://127.0.0.1:8300/ in a clean browser window/tab, sized to fill
the recording frame. Have a second terminal ready (small, off to the
side or on another virtual desktop) with:

```
cd path/to/supervised-ops-demo
./bin/demo-inject "My kitchen faucet has been dripping constantly for two days, would like it looked at when convenient." "Taylor Brooks" "taylor.brooks@example.com" "webform"
```

typed but NOT yet submitted -- you'll run it live at minute ~0:40.

## 0:00 -- 0:15 -- Open on the dashboard, set the scene

**Show:** the full dashboard: stat tiles, both queues, the lead list,
the audit trail panel at the bottom.

**Say:** "This is Bluejay Property Management's inbox -- a fictional
property manager, but the pattern is real. Every inquiry that comes in
gets read, categorized, and drafted by an AI, automatically. But nothing
goes out until a human clicks approve. That's the whole pitch: the AI
does the work, the human stays in control."

Point at the **AI brain online** banner at the top -- "and if the AI
ever goes down, the app doesn't break, it just switches to manual mode."

## 0:15 -- 0:30 -- The escalation queue (the safety story)

**Show:** click into the **Needs Human Review** queue, open the Robert
Chu / noise-complaint lead (or whichever high-urgency complaint is
seeded).

**Say:** "This one never got an AI draft at all. High-urgency complaints
route straight to a human, no matter how confident the AI is -- because
some messages are legal/reputational risk, not a drafting task. That's a
hard rule, not a suggestion."

## 0:30 -- 0:40 -- The money shot: approve / edit / reject

**Show:** click a lead in **Awaiting Approval** (e.g. Priya's leasing
inquiry). Show the AI draft. Click **Edit**, tweak one sentence, click
**Save edit & send**. Then open a second drafted lead and click
**Approve as-is** for contrast.

**Say:** "This is the actual product: read it, fix it if you want, click
once. Every one of these three paths -- approve, edit, reject -- is
logged separately, so there's a real record of what the AI proposed
versus what actually went to the customer."

## 0:40 -- 1:00 -- A live inquiry arrives

**Switch** to the prepared terminal, hit enter on `bin/demo-inject`.

**Say (while it runs, ~5-15s):** "Let's send in a brand-new message right
now, live -- no pre-scripting." Switch back to the dashboard tab; it
polls every few seconds, so the new lead appears in the list on its own.

**Show:** open the new lead -- point out the category/urgency/confidence
badges and, if it drafted, the **knowledge-base context** line showing
which company policy snippet grounded the reply (e.g. maintenance SLA).
Approve it.

## 1:00 -- 1:15 -- Knowledge base

**Show:** click **Knowledge Base** in the nav, type a query like `pet
deposit` or `late fee`.

**Say:** "The AI's drafts are grounded in the company's actual policies --
office hours, SLAs, pet policy, lease renewal -- not just making things
up. This is a simple keyword search under the hood, on purpose: no
external service, fully self-contained."

## 1:15 -- 1:30 -- Follow-up reminders

**Show:** scroll to the **Needs Follow-up** queue -- point out the
overdue badge on a couple of leads that have been sitting untouched.

**Say:** "If a lead sits without an owner action past a configurable
window -- four hours in production, shortened here so you can see it on
camera -- it gets flagged so nothing falls through the cracks."

## 1:30 -- 1:45 -- Daily owner summary

**Show:** click **Generate owner summary** in the right rail, wait for
the real result (~5-15s), read a line or two aloud.

**Say:** "And every day, the owner gets a plain-English summary of what
came in and what still needs attention -- in production this runs on a
schedule and lands in their email; here it's a button so you can see it
happen live."

## 1:45 -- 2:00 -- Close on the audit trail

**Show:** scroll to the **Full Audit Trail** panel at the bottom, scroll
through a few entries -- received, classified, drafted, approved, edited,
escalated, reminder fired.

**Say:** "And this is the part that actually matters for trust: every
single one of those actions -- what the AI did, what the human did -- is
in an append-only log. Nothing is quietly overwritten. If a client ever
asks 'wait, did a human actually see this before it went out,' the
answer is always in here, not in someone's memory."

**End on:** the dashboard, brain-online banner, a clean queue.

## After recording

`./bin/demo-reset` to restore the pristine seed state before the next
take or the next client demo.
