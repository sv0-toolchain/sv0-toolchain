/**
 * Load milestone orientation + task digest for the local progress dashboard.
 * Polls on an interval from /api/config (non-intensive: server caches scans).
 */
async function loadJson(url) {
  const r = await fetch(url);
  if (!r.ok) {
    throw new Error(`${url}: ${r.status}`);
  }
  return r.json();
}

function el(tag, attrs, children) {
  const n = document.createElement(tag);
  if (attrs) {
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === "className") {
        n.className = v;
      } else if (k === "text") {
        n.textContent = v;
      } else {
        n.setAttribute(k, String(v));
      }
    });
  }
  (children || []).forEach((c) => n.appendChild(c));
  return n;
}

function renderMilestones(data) {
  const host = document.getElementById("milestone-cards");
  host.innerHTML = "";
  const milestones = data.milestones || [];
  milestones.forEach((m) => {
    const tasks = (m.primary_tasks || []).map((p) =>
      el("li", {}, [document.createTextNode(p)]),
    );
    const card = el("article", { className: "card" }, [
      el("h3", { text: m.title || m.id }),
      el("div", { className: "id", text: m.id }),
      el("ul", {}, tasks),
    ]);
    host.appendChild(card);
  });
}

function renderDigest(rows) {
  const tbody = document.querySelector("#digest-table tbody");
  tbody.innerHTML = "";
  let errFiles = 0;
  let warnFiles = 0;
  rows.forEach((row) => {
    const e = row.errors || [];
    const w = row.warnings || [];
    if (e.length) {
      errFiles += 1;
    }
    if (w.length) {
      warnFiles += 1;
    }
    const errCell =
      e.length === 0
        ? el("span", { className: "ok", text: "0" })
        : el("span", { className: "err", text: String(e.length) });
    const warnCell =
      w.length === 0
        ? el("span", { className: "ok", text: "0" })
        : el("span", { className: "warn", text: String(w.length) });
    const tr = el("tr", {}, [
      el("td", { className: "path" }, [
        document.createTextNode(row.path || ""),
      ]),
      el("td", { className: "num" }, [
        document.createTextNode(String((row.anchors || []).length)),
      ]),
      el("td", { className: "num" }, [
        document.createTextNode(String((row.checklist_items || []).length)),
      ]),
      el("td", {}, [errCell]),
      el("td", {}, [warnCell]),
    ]);
    tbody.appendChild(tr);
  });
  const summary = document.getElementById("digest-summary");
  summary.textContent = `${rows.length} task file(s) · ${errFiles} with errors · ${warnFiles} with warnings`;
  document.getElementById("digest-pre").textContent = JSON.stringify(
    rows,
    null,
    2,
  );
}

function setRefreshStatus(message) {
  const n = document.getElementById("refresh-status");
  if (n) {
    n.textContent = message;
  }
}

async function loadAndRender() {
  const [milestones, digest] = await Promise.all([
    loadJson("/api/milestones"),
    loadJson("/api/digest"),
  ]);
  renderMilestones(milestones);
  renderDigest(Array.isArray(digest) ? digest : []);
  const t = new Date();
  setRefreshStatus(`Last updated ${t.toLocaleTimeString()} (local)`);
}

async function main() {
  let pollMs = 120000;
  try {
    const cfg = await loadJson("/api/config");
    if (cfg && typeof cfg.suggested_client_poll_ms === "number") {
      pollMs = cfg.suggested_client_poll_ms;
    }
  } catch {
    /* use default */
  }
  try {
    await loadAndRender();
  } catch (e) {
    document
      .querySelector("main")
      .prepend(
        el("p", { className: "err" }, [
          document.createTextNode(`Failed to load data: ${e.message}`),
        ]),
      );
    return;
  }
  const rs = document.getElementById("refresh-status");
  const base = rs ? rs.textContent.trim() : "";
  const pollSec = Math.round(pollMs / 1000);
  setRefreshStatus(`${base} · auto-refresh ~${pollSec}s`);
  window.setInterval(() => {
    loadAndRender().catch((e) => {
      setRefreshStatus(`Refresh failed: ${e.message}`);
    });
  }, pollMs);
}

main();
