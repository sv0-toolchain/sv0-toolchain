/**
 * Progress dashboard: milestones + per-file digest with progressive disclosure.
 * Poll interval from /api/config when available.
 */

/** @type {Array<Record<string, unknown>> | null} */
let lastDigestRows = null;

/**
 * @param {string} url
 * @returns {Promise<unknown>}
 */
async function loadJson(url) {
  const r = await fetch(url);
  if (!r.ok) {
    throw new Error(`${url}: ${r.status}`);
  }
  return r.json();
}

/**
 * @param {string} path
 * @returns {string}
 */
function basename(path) {
  const i = path.lastIndexOf("/");
  return i >= 0 ? path.slice(i + 1) : path;
}

/**
 * @param {HTMLElement} parent
 * @param {string} tag
 * @param {Record<string, string> | null} attrs
 * @param {(string | Node)[]} children
 * @returns {HTMLElement}
 */
function el(parent, tag, attrs, children) {
  const n = document.createElement(tag);
  if (attrs) {
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === "className") {
        n.className = v;
      } else if (k === "text") {
        n.textContent = v;
      } else {
        n.setAttribute(k, v);
      }
    });
  }
  (children || []).forEach((c) => {
    n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  });
  if (parent) {
    parent.appendChild(n);
  }
  return n;
}

/**
 * @param {unknown} data
 */
function renderMilestones(data) {
  const host = document.getElementById("milestone-cards");
  if (!host) {
    return;
  }
  host.innerHTML = "";
  const milestones =
    data && typeof data === "object" && "milestones" in data
      ? /** @type {{ milestones?: unknown[] }} */ (data).milestones
      : [];
  if (!Array.isArray(milestones)) {
    return;
  }
  milestones.forEach((m) => {
    if (!m || typeof m !== "object") {
      return;
    }
    const row = /** @type {Record<string, unknown>} */ (m);
    const title = typeof row.title === "string" ? row.title : String(row.id ?? "");
    const id = typeof row.id === "string" ? row.id : "";
    const tasks = Array.isArray(row.primary_tasks) ? row.primary_tasks : [];
    const ul = document.createElement("ul");
    tasks.forEach((p) => {
      if (typeof p !== "string") {
        return;
      }
      const li = document.createElement("li");
      li.textContent = basename(p);
      li.setAttribute("title", p);
      ul.appendChild(li);
    });
    el(host, "article", { className: "m-card" }, [
      el(null, "h3", { text: title }),
      el(null, "div", { className: "m-id", text: id }),
      ul,
    ]);
  });
}

/**
 * @param {Record<string, unknown>} row
 */
function rowIssueScore(row) {
  const e = Array.isArray(row.errors) ? row.errors.length : 0;
  const w = Array.isArray(row.warnings) ? row.warnings.length : 0;
  return e * 1000 + w;
}

/**
 * @param {Record<string, unknown>} row
 * @returns {{ done: number, total: number }}
 */
function checklistProgress(row) {
  const items = Array.isArray(row.checklist_items) ? row.checklist_items : [];
  let done = 0;
  items.forEach((it) => {
    if (it && typeof it === "object" && "done" in it && it.done === true) {
      done += 1;
    }
  });
  return { done, total: items.length };
}

/**
 * @param {Array<Record<string, unknown>>} rows
 */
function renderStatusStrip(rows) {
  const strip = document.getElementById("status-strip");
  if (!strip) {
    return;
  }
  strip.innerHTML = "";
  let errFiles = 0;
  let warnOnly = 0;
  let ckDone = 0;
  let ckTotal = 0;
  rows.forEach((row) => {
    const e = Array.isArray(row.errors) ? row.errors.length : 0;
    const w = Array.isArray(row.warnings) ? row.warnings.length : 0;
    if (e > 0) {
      errFiles += 1;
    } else if (w > 0) {
      warnOnly += 1;
    }
    const { done, total } = checklistProgress(row);
    ckDone += done;
    ckTotal += total;
  });
  el(
    strip,
    "span",
    { className: "stat-pill", role: "presentation" },
    [document.createTextNode("Files scanned "), el(null, "strong", { text: String(rows.length) }, [])],
  );
  if (errFiles > 0) {
    el(
      strip,
      "span",
      { className: "stat-pill stat-err", role: "status" },
      [
        document.createTextNode("Needs fix "),
        el(null, "strong", { text: String(errFiles) }, []),
        document.createTextNode(errFiles === 1 ? " file" : " files"),
      ],
    );
  } else if (warnOnly > 0) {
    el(
      strip,
      "span",
      { className: "stat-pill stat-warn", role: "status" },
      [
        document.createTextNode("Warnings "),
        el(null, "strong", { text: String(warnOnly) }, []),
      ],
    );
  } else {
    el(
      strip,
      "span",
      { className: "stat-pill stat-ok", role: "status" },
      [document.createTextNode("No digest errors")],
    );
  }
  if (ckTotal > 0) {
    el(
      strip,
      "span",
      { className: "stat-pill", role: "presentation" },
      [
        document.createTextNode("Checklist "),
        el(null, "strong", { text: `${ckDone} / ${ckTotal}` }, []),
        document.createTextNode(" done"),
      ],
    );
  }
}

/**
 * @param {Record<string, unknown>} row
 * @returns {HTMLElement}
 */
function buildDigestCard(row) {
  const path = typeof row.path === "string" ? row.path : "";
  const base = basename(path);
  const errors = Array.isArray(row.errors) ? row.errors : [];
  const warnings = Array.isArray(row.warnings) ? row.warnings : [];
  const anchors = Array.isArray(row.anchors) ? row.anchors : [];
  const items = Array.isArray(row.checklist_items) ? row.checklist_items : [];
  const { done, total } = checklistProgress(row);

  const errN = errors.length;
  const warnN = warnings.length;
  let statusClass = "badge-clear";
  let statusText = "OK";
  if (errN > 0) {
    statusClass = "badge-err";
    statusText = `${errN} error${errN === 1 ? "" : "s"}`;
  } else if (warnN > 0) {
    statusClass = "badge-warn";
    statusText = `${warnN} warning${warnN === 1 ? "" : "s"}`;
  }

  const details = document.createElement("details");
  details.className = "digest-card";
  if (errN > 0) {
    details.classList.add("issue");
  } else if (warnN > 0) {
    details.classList.add("issue-warn");
  }

  const summary = document.createElement("summary");
  const titleWrap = el(null, "div", { className: "card-title" }, []);
  el(titleWrap, "span", { className: "card-basename", text: base }, []);
  el(titleWrap, "span", { className: "card-path", text: path }, []);

  const meta = el(null, "div", { className: "card-meta" }, []);
  el(meta, "span", { className: `badge ${statusClass}`, text: statusText }, []);
  if (total > 0) {
    el(
      meta,
      "span",
      { className: "badge badge-muted", text: `${done}/${total} done` },
      [],
    );
  } else {
    el(meta, "span", { className: "badge badge-muted", text: "No checklists" }, []);
  }

  summary.appendChild(titleWrap);
  summary.appendChild(meta);
  details.appendChild(summary);

  const body = el(null, "div", { className: "digest-card-body" }, []);

  if (anchors.length > 0) {
    el(
      body,
      "p",
      { className: "anchor-note" },
      [
        document.createTextNode(
          `${anchors.length} tracking anchor${anchors.length === 1 ? "" : "s"} in this file.`,
        ),
      ],
    );
  }

  if (items.length === 0) {
    el(
      body,
      "p",
      { className: "empty" },
      [
        document.createTextNode(
          "No GFM checklist lines are bound to sv0-track yet. Add a region with ingest \"gfm\" in this task file to see rows here.",
        ),
      ],
    );
  } else {
    const ul = el(body, "ul", { className: "checklist" }, []);
    items.forEach((raw) => {
      if (!raw || typeof raw !== "object") {
        return;
      }
      const it = /** @type {Record<string, unknown>} */ (raw);
      const isDone = it.done === true;
      const text = typeof it.text === "string" ? it.text : "";
      const li = el(ul, "li", { className: isDone ? "done" : "" }, []);
      el(li, "span", { className: "box", "aria-hidden": "true" }, []);
      const line =
        typeof it.line === "number"
          ? `Line ${it.line}: `
          : "";
      el(li, "span", { className: "txt", text: line + text }, []);
    });
  }

  if (errN > 0 || warnN > 0) {
    const pre = el(
      body,
      "pre",
      {
        className: "digest-pre",
        style: "margin-top:0.75rem;max-height:12rem;font-size:0.68rem;",
      },
      [],
    );
    const lines = [];
    errors.forEach((x) => lines.push(String(x)));
    warnings.forEach((x) => lines.push(String(x)));
    pre.textContent = lines.join("\n");
  }

  details.appendChild(body);
  return details;
}

/**
 * @param {Array<Record<string, unknown>>} rows
 * @param {boolean} issuesOnly
 */
function renderDigestCards(rows, issuesOnly) {
  const host = document.getElementById("digest-cards");
  if (!host) {
    return;
  }
  host.innerHTML = "";
  const sorted = [...rows].sort((a, b) => {
    const da = rowIssueScore(a);
    const db = rowIssueScore(b);
    if (db !== da) {
      return db - da;
    }
    const pa = typeof a.path === "string" ? a.path : "";
    const pb = typeof b.path === "string" ? b.path : "";
    return pa.localeCompare(pb);
  });
  const filtered = issuesOnly
    ? sorted.filter((r) => {
        const e = Array.isArray(r.errors) ? r.errors.length : 0;
        const w = Array.isArray(r.warnings) ? r.warnings.length : 0;
        return e > 0 || w > 0;
      })
    : sorted;
  filtered.forEach((row) => {
    host.appendChild(buildDigestCard(row));
  });
  if (filtered.length === 0 && issuesOnly) {
    el(
      host,
      "p",
      { className: "panel-hint" },
      [document.createTextNode("No files with errors or warnings — turn off the filter to see all tasks.")],
    );
  }
}

/**
 * @param {Array<Record<string, unknown>>} rows
 */
function renderDigest(rows) {
  lastDigestRows = rows;
  renderStatusStrip(rows);
  const pre = document.getElementById("digest-pre");
  if (pre) {
    pre.textContent = JSON.stringify(rows, null, 2);
  }
  const issuesOnly =
    document.getElementById("filter-issues") instanceof HTMLInputElement
      ? /** @type {HTMLInputElement} */ (document.getElementById("filter-issues")).checked
      : false;
  renderDigestCards(rows, issuesOnly);
}

/**
 * @param {string} message
 */
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
  const rows = Array.isArray(digest) ? digest : [];
  renderDigest(/** @type {Array<Record<string, unknown>>} */ (rows));
  const t = new Date();
  setRefreshStatus(`Last updated ${t.toLocaleTimeString()} (local)`);
}

async function main() {
  const filter = document.getElementById("filter-issues");
  if (filter instanceof HTMLInputElement && lastDigestRows === null) {
    filter.addEventListener("change", () => {
      if (lastDigestRows) {
        renderDigest(lastDigestRows);
      }
    });
  }

  let pollMs = 120000;
  try {
    const cfg = await loadJson("/api/config");
    if (cfg && typeof cfg === "object" && "suggested_client_poll_ms" in cfg) {
      const v = /** @type {{ suggested_client_poll_ms?: unknown }} */ (cfg)
        .suggested_client_poll_ms;
      if (typeof v === "number") {
        pollMs = v;
      }
    }
  } catch {
    /* use default */
  }
  try {
    await loadAndRender();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const page = document.querySelector(".page") || document.body;
    el(page, "p", { className: "banner-err", role: "alert" }, [
      document.createTextNode(`Could not load dashboard data: ${msg}`),
    ]);
    return;
  }
  const rs = document.getElementById("refresh-status");
  const base = rs ? rs.textContent.trim() : "";
  const pollSec = Math.round(pollMs / 1000);
  setRefreshStatus(`${base} · refreshes about every ${pollSec}s`);
  window.setInterval(() => {
    loadAndRender().catch((err) => {
      const m = err instanceof Error ? err.message : String(err);
      setRefreshStatus(`Refresh failed: ${m}`);
    });
  }, pollMs);
}

main();
