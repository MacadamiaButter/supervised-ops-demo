/*
 * Self-running sales-demo tour.
 *
 * Activated by ?tour=1 on the dashboard route (or the /tour redirect).
 * No-ops entirely -- zero DOM, zero listeners -- unless that param is
 * present, so it's safe to include unconditionally from base.html.
 *
 * Two modes:
 *   ?tour=1              -- LIVE. The one inject and the one summary
 *                            call in the storyboard go to the real brain
 *                            (5-40s each). Good for an in-person demo.
 *   ?tour=1&canned=1      -- CANNED. Same two calls carry a "canned"
 *                            flag the backend understands (see
 *                            app.pipeline.process_new_inquiry /
 *                            app.main.api_generate_summary) and get
 *                            fixed, near-instant responses from
 *                            app/fixtures.py instead. This is what
 *                            bin/record-demo drives, so a recorded take
 *                            has fixed timing and fixed on-screen text.
 *
 * On completion the engine sets document.body.dataset.tourDone = "1"
 * and fires a "tour:done" CustomEvent on window -- bin/record-demo's
 * Playwright driver polls for that attribute to know when to stop
 * recording and exit.
 *
 * The storyboard itself is the declarative TOUR beats below the engine
 * (search for "THE STORYBOARD") -- captions/selectors/actions only, so
 * it can be re-scripted without touching the move/click/glow/caption
 * primitives above it. It follows DEMO-SCRIPT.md, compressed to ~100-120s.
 */

(function () {
  const params = new URLSearchParams(window.location.search);
  if (params.get("tour") !== "1") return;
  const CANNED = params.get("canned") === "1";

  // ---- tunable pacing ----------------------------------------------------
  // One knob (PACE) to speed the whole thing up/down uniformly if the
  // total runtime drifts outside the ~100-120s target during tuning.
  const PACE = 1.5;
  const MS_PER_WORD = 430 * PACE;
  const MIN_CAPTION_MS = 2000 * PACE;
  const CURSOR_MOVE_MS = 750 * PACE;
  const SCROLL_SETTLE_MS = 380 * PACE;
  const CAPTION_FADE_GAP_MS = 320 * PACE;
  const BEAT_PAUSE_MS = 450 * PACE;
  const CANNED_MIN_THINK_MS = 1100 * PACE;

  // ---- tiny engine --------------------------------------------------------

  let cursorEl, captionEl, captionTextEl;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function buildOverlay() {
    const root = document.createElement("div");
    root.id = "tour-overlay";
    root.innerHTML = '<div id="tour-cursor" aria-hidden="true"></div>' +
      '<div id="tour-caption"><div id="tour-caption-text"></div></div>';
    document.body.appendChild(root);

    const finalCard = document.createElement("div");
    finalCard.id = "tour-final-card";
    document.body.appendChild(finalCard);

    cursorEl = document.getElementById("tour-cursor");
    captionEl = document.getElementById("tour-caption");
    captionTextEl = document.getElementById("tour-caption-text");
    positionCursor(window.innerWidth / 2, window.innerHeight * 0.4);
  }

  function positionCursor(x, y) {
    cursorEl.style.transform = "translate(" + x + "px, " + y + "px)";
  }

  function centerOf(el) {
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + Math.min(r.height / 2, 40) };
  }

  function resolveEl(selector) {
    return typeof selector === "string" ? document.querySelector(selector) : selector;
  }

  async function moveCursorTo(selector) {
    const el = resolveEl(selector);
    if (!el) return null;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    await sleep(SCROLL_SETTLE_MS);
    const { x, y } = centerOf(el);
    cursorEl.style.transition = "transform " + CURSOR_MOVE_MS + "ms cubic-bezier(.4,0,.2,1)";
    positionCursor(x, y);
    await sleep(CURSOR_MOVE_MS);
    return el;
  }

  function rippleAt(x, y) {
    const ripple = document.createElement("div");
    ripple.className = "tour-click-ripple";
    ripple.style.left = x + "px";
    ripple.style.top = y + "px";
    document.body.appendChild(ripple);
    setTimeout(function () { ripple.remove(); }, 650);
  }

  async function clickEl(selector) {
    const el = await moveCursorTo(selector);
    if (!el) return null;
    const { x, y } = centerOf(el);
    rippleAt(x, y);
    await sleep(200);
    el.click();
    return el;
  }

  function glow(selector, on) {
    const el = resolveEl(selector);
    if (!el) return;
    el.classList.toggle("tour-highlight", !!on);
  }

  async function caption(text, opts) {
    opts = opts || {};
    const words = text.trim().split(/\s+/).length;
    const duration = opts.duration || Math.max(MIN_CAPTION_MS, words * MS_PER_WORD);
    captionTextEl.textContent = text;
    captionEl.classList.add("show");
    await sleep(duration);
    if (!opts.keep) {
      captionEl.classList.remove("show");
      await sleep(CAPTION_FADE_GAP_MS);
    }
  }

  function setThinking(on, label) {
    if (on) {
      captionTextEl.textContent = label || "AI thinking...";
      captionEl.classList.add("show", "tour-thinking");
    } else {
      captionEl.classList.remove("tour-thinking");
    }
  }

  async function withMinDuration(promise, minMs) {
    const [, result] = await Promise.all([sleep(minMs), promise]);
    return result;
  }

  // ---- app integration ----------------------------------------------------

  async function injectTourInquiry() {
    const body = {
      customer_name: "Taylor Brooks",
      customer_contact: "taylor.brooks@example.com",
      channel: "webform",
      raw_text:
        "My kitchen faucet has been dripping constantly for two days, " +
        "would like it looked at when convenient.",
      canned: CANNED,
    };
    const req = fetch("/api/inquiries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); });
    const result = await withMinDuration(req, CANNED ? CANNED_MIN_THINK_MS : 0);
    if (typeof refreshDashboard === "function") refreshDashboard();
    await sleep(500); // let the #dashboard-live fragment swap settle
    return result;
  }

  async function runOwnerSummary() {
    // Reuses app.js's generateSummary() so the button/box states (the
    // "Asking the brain..." pending text) stay the single source of
    // truth -- the tour just drives the same function a real click would.
    if (typeof generateSummary !== "function") return null;
    return withMinDuration(generateSummary(CANNED), CANNED ? CANNED_MIN_THINK_MS : 0);
  }

  async function showFinalCard() {
    const card = document.getElementById("tour-final-card");
    card.innerHTML =
      '<div class="tour-final-inner">' +
      "<h2>Supervised AI operations: your hours back, your control intact.</h2>" +
      "<p>Bluejay Property Management is a fictional company built for this demo &mdash; the pattern is real.</p>" +
      '<p class="tour-contact-placeholder">hello@localfirstlab.org &middot; localfirstlab.org</p>' +
      "</div>";
    card.classList.add("show");
    await sleep(6000 * PACE);
  }

  // ---- THE STORYBOARD -------------------------------------------------
  // Mirrors DEMO-SCRIPT.md's beats 1-7, compressed. Each beat is just
  // moveCursorTo/clickEl/glow/caption calls -- re-order or reword freely.

  async function showIntroCard() {
    // Owner feedback 2026-07-12: open with context so a first-time viewer
    // knows what they're looking at (and buying) before the UI appears.
    const card = document.getElementById("tour-final-card"); // reused container
    card.innerHTML =
      '<div class="tour-final-inner">' +
      "<h2>What you're about to see</h2>" +
      "<p>A <strong>supervised AI operations system</strong>, installed for a small " +
      "property-management company. It watches the channels customers already use " +
      "&mdash; contact form and email &mdash; and turns every message into a triaged, " +
      "draft-answered, tracked lead.</p>" +
      "<p>The AI classifies each inquiry, drafts a reply from the company's own " +
      "policies, and chases forgotten leads. <strong>A human approves everything " +
      "before it goes out.</strong> You'll see all of it in the next two minutes.</p>" +
      "</div>";
    card.classList.add("show");
    await sleep(11000 * PACE);
    card.classList.remove("show");
    card.innerHTML = "";
    await sleep(600 * PACE);
  }

  async function runTour() {
    buildOverlay();
    await sleep(700 * PACE);

    // 0) Intro context card
    await showIntroCard();

    // 1) Dashboard overview
    await moveCursorTo(".stat-row");
    glow(".stat-row", true);
    await caption("Every customer inquiry lands here — nothing is ever sent automatically.");
    glow(".stat-row", false);
    await sleep(BEAT_PAUSE_MS);

    // 2) A new inquiry arrives, live
    await caption("Let's send in a brand-new inquiry, live, right now.", { duration: 2400 * PACE });
    setThinking(true, CANNED ? "Classifying the new message..." : "AI thinking … classifying the new message (a real call to the brain)");
    const created = await injectTourInquiry();
    setThinking(false);
    const newId = created && created.id;
    if (newId != null) {
      const row = await moveCursorTo('[data-lead-id="' + newId + '"]');
      if (row) glow(row, true);
      await caption("The AI triages it in seconds: category, urgency, and confidence.");
      if (row) glow(row, false);
    }
    await sleep(BEAT_PAUSE_MS);

    // 3) Open the lead -- the AI-drafted reply
    if (newId != null) {
      await clickEl('[data-lead-id="' + newId + '"]');
      await sleep(450 * PACE);
      glow("#detail-panel", true);
      await caption("The AI drafts a reply from your company's own policies — grounded, not improvised.");
      glow("#detail-panel", false);

      // 4) THE MONEY SHOT -- the approval gate
      await moveCursorTo("#detail-panel .btn-approve");
      glow("#detail-panel .action-row", true);
      await caption("Nothing reaches your customer until a human clicks Approve. That's the whole point.", { keep: true });
      await sleep(900 * PACE);
      captionEl.classList.remove("show");
      glow("#detail-panel .action-row", false);
      await sleep(CAPTION_FADE_GAP_MS);
      await clickEl("#detail-panel .btn-approve");
      await sleep(650 * PACE);
    }
    await sleep(BEAT_PAUSE_MS);

    // 5) Escalation queue (the safety story)
    await moveCursorTo(".queue-card.needs-human");
    glow(".queue-card.needs-human", true);
    await caption("When the AI isn't sure — or the stakes are high — it doesn't guess. It escalates to a human instead.");
    // Prefer the pre-seeded high-urgency complaint (Robert Chu in the
    // stock seed data) so the beat matches DEMO-SCRIPT.md's "safety
    // story"; fall back to whichever needs-human row exists otherwise.
    const escalatedRow =
      document.querySelector(".queue-card.needs-human .lead-row:has(.urgency-high)") ||
      document.querySelector(".queue-card.needs-human .lead-row");
    if (escalatedRow) {
      await clickEl(escalatedRow);
      await sleep(450 * PACE);
    }
    glow(".queue-card.needs-human", false);
    await sleep(BEAT_PAUSE_MS);

    // 6) Audit trail
    await moveCursorTo("#audit-trail-card");
    glow("#audit-trail-card", true);
    await caption("Every single action is logged here. You can always answer: why did the system do that?");
    glow("#audit-trail-card", false);
    await sleep(BEAT_PAUSE_MS);

    // 7) Daily owner summary, then close
    await moveCursorTo("#gen-summary-btn");
    glow(".summary-card", true);
    await runOwnerSummary();
    await caption("And every day, the owner gets a plain-English summary of what came in and what still needs attention.");
    glow(".summary-card", false);

    await showFinalCard();

    document.body.dataset.tourDone = "1";
    window.dispatchEvent(new CustomEvent("tour:done"));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { runTour(); });
  } else {
    runTour();
  }
})();
