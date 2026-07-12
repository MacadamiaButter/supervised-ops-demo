/*
 * Small vanilla-JS helpers -- no framework, no build step, htmx-style
 * manual fetch-and-swap. Two live behaviors matter for the demo:
 *   1. The dashboard fragment (#dashboard-live) polls every 4s so a
 *      follow-up reminder or a newly-injected inquiry (bin/demo-inject)
 *      appears without a manual page refresh during the recording.
 *   2. Opening a lead fetches its detail fragment into #detail-panel;
 *      approve/edit/reject post back, then both panels refresh.
 */

let currentLeadId = null;

function refreshDashboard() {
  fetch("/partials/leads")
    .then((r) => r.text())
    .then((html) => {
      document.getElementById("dashboard-live").innerHTML = html;
    })
    .catch(() => {});
}

function startDashboardPolling() {
  refreshDashboard();
  setInterval(refreshDashboard, 4000);
}

function openLead(id) {
  currentLeadId = id;
  fetch(`/inquiry/${id}`)
    .then((r) => r.text())
    .then((html) => {
      const panel = document.getElementById("detail-panel");
      panel.classList.remove("empty");
      panel.innerHTML = html;
    });
}

function refreshOpenLead() {
  if (currentLeadId != null) {
    openLead(currentLeadId);
  }
}

function approveLead(id) {
  fetch(`/inquiry/${id}/approve`, { method: "POST" }).then(() => {
    refreshOpenLead();
    refreshDashboard();
  });
}

function rejectLead(id) {
  const reason = prompt("Reason for rejecting this draft? (optional)", "");
  const body = new URLSearchParams();
  body.set("reason", reason || "");
  fetch(`/inquiry/${id}/reject`, { method: "POST", body }).then(() => {
    refreshOpenLead();
    refreshDashboard();
  });
}

function toggleEdit() {
  const readonly = document.getElementById("draft-readonly");
  const editor = document.getElementById("reply-editor");
  const actions = document.getElementById("edit-actions");
  if (!editor) return;
  const showing = editor.style.display !== "none";
  editor.style.display = showing ? "none" : "block";
  if (readonly) readonly.style.display = showing ? "block" : "none";
  actions.style.display = showing ? "none" : "flex";
}

function submitEdit(id) {
  const editor = document.getElementById("reply-editor");
  const text = editor ? editor.value : "";
  if (!text.trim()) {
    alert("Reply text can't be empty.");
    return;
  }
  const body = new URLSearchParams();
  body.set("final_text", text);
  fetch(`/inquiry/${id}/edit`, { method: "POST", body }).then(() => {
    refreshOpenLead();
    refreshDashboard();
  });
}

function generateSummary(canned) {
  // canned=true is used only by static/tour.js's ?tour=1&canned=1 mode --
  // it hits the same endpoint with ?canned=1 so the backend returns the
  // fixed app.fixtures summary instead of calling the real brain. Returns
  // the fetch promise so callers (the tour engine) can await completion.
  const box = document.getElementById("summary-result");
  const btn = document.getElementById("gen-summary-btn");
  box.className = "pending";
  box.textContent = "Asking the brain to summarize today's leads... (a real call, can take up to ~30s)";
  btn.disabled = true;
  const url = canned ? "/api/summary?canned=1" : "/api/summary";
  return fetch(url, { method: "POST" })
    .then((r) => r.json())
    .then((data) => {
      btn.disabled = false;
      if (data.ok) {
        box.className = "";
        box.textContent = data.summary;
      } else {
        box.className = "error";
        box.textContent = "Summary unavailable: " + data.error;
      }
      return data;
    })
    .catch((err) => {
      btn.disabled = false;
      box.className = "error";
      box.textContent = "Summary unavailable: " + err;
    });
}

let kbDebounce = null;
document.addEventListener("DOMContentLoaded", () => {
  const kbInput = document.getElementById("kb-mini-q");
  if (kbInput) {
    kbInput.addEventListener("input", () => {
      clearTimeout(kbDebounce);
      const q = kbInput.value.trim();
      const resultsBox = document.getElementById("kb-mini-results");
      if (!q) {
        resultsBox.innerHTML = "";
        return;
      }
      kbDebounce = setTimeout(() => {
        fetch(`/api/kb/search?q=${encodeURIComponent(q)}`)
          .then((r) => r.json())
          .then((data) => {
            resultsBox.innerHTML = data.results
              .map(
                (r) =>
                  `<div class="kb-mini-result"><div class="kb-title">${r.title}</div>${r.snippet}</div>`
              )
              .join("") || `<p class="empty-note">No matches.</p>`;
          });
      }, 250);
    });
  }
});
