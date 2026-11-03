/* NinjaDash wall display: fetches /api/summary every 30 s and draws the 1920x1080 screen. */
(function () {
  "use strict";
  const REFRESH_MS = 30000;

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const svg = (p, s = 16) => `<svg width="${s}" height="${s}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
  const CAT = {
    hardware:  s => svg('<rect x="2" y="3.5" width="12" height="9" rx="2"/><path d="M2 9h12"/><circle cx="11.3" cy="11" r=".6" fill="currentColor"/>', s),
    backup:    s => svg('<path d="M13.2 8.4A5.2 5.2 0 1 1 11.7 4.3"/><path d="M12.4 1.8v2.9H9.5"/><path d="M8 5.5V8l1.7 1.2"/>', s),
    antivirus: s => svg('<path d="M8 1.8 13.2 3.7v3.9c0 3-2.2 5.3-5.2 6.6-3-1.3-5.2-3.6-5.2-6.6V3.7z"/><path d="M5.8 8l1.5 1.5 2.9-3"/>', s),
    offline:   s => svg('<path d="M8 1.8v5.4"/><path d="M4.4 4.3a5.2 5.2 0 1 0 7.2 0"/>', s),
    other:     s => svg('<circle cx="8" cy="8" r="6.2"/><path d="M8 4.8v3.6"/><circle cx="8" cy="11" r=".6" fill="currentColor"/>', s)
  };
  const CATNAME = { hardware: "Hardware", backup: "Backup", antivirus: "Antivirus", offline: "Offline", other: "Other" };
  const SEV = {
    critical: '<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor"/><rect x="7" y="3.6" width="2" height="5.6" rx="1" fill="#fff"/><circle cx="8" cy="11.6" r="1.1" fill="#fff"/></svg>',
    warning:  '<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.8 14.6 13.6H1.4z" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><rect x="7.1" y="5.6" width="1.8" height="4.4" rx=".9" fill="#fff"/><circle cx="8" cy="11.8" r=".95" fill="#fff"/></svg>',
    ok:       '<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor"/><path d="M5 8.2l2 2 4-4.2" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    offline:  '<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M5 8h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
  };
  const BIG_OK = SEV.ok.replace(/width="14" height="14"/, 'width="28" height="28"');
  const WORD = { critical: "Critical", warning: "Warning", ok: "All clear", offline: "Offline", minor: "Minor" };
  const STATEVAR = { critical: "var(--critical)", warning: "var(--warning)", ok: "var(--good)", offline: "var(--offline)" };
  const plural = (n, w) => (n === 1 ? w : w + "s");
  const chip = s => `<span class="chip ${s}"><span class="ic">${SEV[s] || SEV.warning}</span>${WORD[s] || s}</span>`;
  const sum = a => (a || []).reduce((x, y) => x + y, 0);

  let data = null, fetchError = null, previousCritical = new Set();

  function ago(epoch) {
    if (!epoch) return "";
    const s = Math.max(0, Date.now() / 1000 - epoch);
    if (s < 60) return "now";
    if (s < 3600) return Math.floor(s / 60) + " min";
    if (s < 48 * 3600) return Math.floor(s / 3600) + " h";
    return Math.floor(s / 86400) + " d";
  }
  function issueText(i) {
    if (i.category === "offline") return "Not responding";
    return i.text;
  }

  // ---- theme ------------------------------------------------------------------
  function minutes(hhmm) { const [h, m] = String(hhmm || "0:0").split(":").map(Number); return (h || 0) * 60 + (m || 0); }
  function applyTheme() {
    const t = (data && data.theme) || { mode: "auto", lightFrom: "07:00", lightUntil: "19:00" };
    let mode = t.mode;
    if (mode !== "light" && mode !== "dark") {
      const now = new Date(), m = now.getHours() * 60 + now.getMinutes();
      const a = minutes(t.lightFrom), b = minutes(t.lightUntil);
      mode = (a <= b ? m >= a && m < b : m >= a || m < b) ? "light" : "dark";
    }
    if (document.documentElement.dataset.theme !== mode) document.documentElement.dataset.theme = mode;
  }

  // ---- scale the 1920x1080 canvas to the screen ----------------------------------
  function fit() {
    const scale = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
    document.getElementById("screen").style.transform = `scale(${scale})`;
  }
  window.addEventListener("resize", fit);

  // ---- status pill + clock -------------------------------------------------------
  function statusPill() {
    if (fetchError) return { cls: "down", text: fetchError };
    if (!data) return { cls: "stale", text: "Connecting…" };
    if (data.setupNeeded) return { cls: "demo", text: "Example data · connect NinjaOne with: sudo ninjadash edit" };
    if (data.demo) return { cls: "demo", text: "Example data (demo mode)" };
    if (!data.lastSuccess) return { cls: data.error ? "down" : "stale", text: data.error ? `Not connected · ${data.error}` : "Connecting to NinjaOne…" };
    const age = Date.now() / 1000 - data.lastSuccess;
    const when = age < 5 ? "just now" : age < 90 ? `${Math.round(age)} s ago` : `${Math.round(age / 60)} min ago`;
    if (age > 15 * 60) return { cls: "down", text: `Last NinjaOne sync ${when}${data.error ? " · " + data.error : ""}` };
    if (age > 5 * 60) return { cls: "stale", text: `Last NinjaOne sync ${when}${data.error ? " · " + data.error : ""}` };
    return { cls: "", text: `NinjaOne synced ${when}` };
  }
  function tick() {
    const now = new Date();
    const t = document.getElementById("clock-time"), d = document.getElementById("clock-date"), p = document.getElementById("status");
    if (t) t.textContent = now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    if (d) d.textContent = now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
    if (p) { const s = statusPill(); p.className = "pill " + s.cls; p.querySelector(".txt").textContent = s.text; p.title = s.text; }
    applyTheme();
  }

  // ---- drawing ---------------------------------------------------------------------
  function columns(values, w, h) {
    const n = values.length, slot = w / n, bw = Math.min(14, slot - 6), top = 16, base = h - 2;
    const max = Math.max(4, ...values), y = v => base - v / max * (base - top);
    let s = `<svg width="${w}" height="${h}" aria-hidden="true"><line x1="0" x2="${w}" y1="${base}" y2="${base}" stroke="var(--axis)"/>`;
    values.forEach((v, i) => {
      const x0 = slot * i + (slot - bw) / 2, last = i === n - 1;
      const fill = last ? "var(--accent)" : "color-mix(in srgb, var(--accent) 45%, var(--card))";
      if (v > 0) {
        const y1 = y(v), r = Math.min(3, (base - y1) / 2);
        s += `<path d="M${x0},${base} V${y1 + r} Q${x0},${y1} ${x0 + r},${y1} H${x0 + bw - r} Q${x0 + bw},${y1} ${x0 + bw},${y1 + r} V${base} Z" fill="${fill}"/>`;
      }
      if (last) s += `<text x="${x0 + bw / 2}" y="${y(v) - 4}" text-anchor="middle" fill="var(--text-1)" style="font-size:11px;font-weight:600;font-family:inherit">${v}</text>`;
    });
    return s + "</svg>";
  }

  function render() {
    const D = data;
    if (!D || !D.ready) {
      document.getElementById("screen").innerHTML = header(D) + `<div class="boot" style="grid-row: 2 / -1">${esc(D && D.error ? D.error : "Loading data from NinjaOne…")}</div>`;
      tick();
      return;
    }
    const affected = D.affected || [], healthy = D.healthy || [], ws = D.workstations || [];
    const serversTotal = (D.online && D.online.servers[1]) || 0, wsTotal = (D.online && D.online.workstations[1]) || 0;
    const dense = affected.length > 6;
    const maxCards = dense ? 15 : 6;
    const shownCards = affected.length > maxCards ? affected.slice(0, maxCards - 1) : affected;
    const hiddenCards = affected.length - shownCards.length;
    const crit = new Set(affected.filter(s => s.state === "critical").map(s => s.org + "/" + s.name));
    const isNew = s => previousCritical.size && s.state === "critical" && !previousCritical.has(s.org + "/" + s.name);

    const pillar = (key, label) => {
      const p = (D.pillars || {})[key] || { servers: 0, workstations: 0, state: "ok", note: "" };
      const total = p.servers + p.workstations, state = total ? p.state : "ok";
      return `<div class="card pillar" style="--state:${STATEVAR[state] || STATEVAR.warning}">
        <div class="top"><div class="label">${CAT[key](18)}${label}</div>${chip(state)}</div>
        <div class="mid"><div class="value">${total}</div><div class="unit">${total === 1 ? "device" : "devices"} affected</div></div>
        <div class="split"><span class="srv"><b>${p.servers}</b> ${plural(p.servers, "server")}</span><span><b>${p.workstations}</b> ${plural(p.workstations, "workstation")}</span><span class="note">${esc(p.note)}</span></div>
      </div>`;
    };
    const srvCard = s => {
      const shown = dense ? s.issues.slice(0, 1) : s.issues.slice(0, 2);
      const extra = s.issues.length - shown.length;
      return `<div class="srv-card${isNew(s) ? " flash" : ""}" style="--state:${STATEVAR[s.state] || STATEVAR.warning}">
        <div class="hd"><div><span class="nm">${esc(s.name)}</span><span class="org">${esc(s.org)}</span></div>${chip(s.state)}</div>
        ${shown.map(i => `<div class="issue">${(CAT[i.category] || CAT.other)(16)}<span>${esc(issueText(i))}</span><span class="since">${ago(i.since)}</span></div>`).join("")}
        ${extra > 0 ? `<div class="more">+${extra} more ${plural(extra, "issue")}</div>` : ""}
      </div>`;
    };
    let healthyHtml;
    if (affected.length > 9 || healthy.length > 120) {
      const byOrg = {};
      healthy.forEach(h => { byOrg[h.org || "No organisation"] = (byOrg[h.org || "No organisation"] || 0) + 1; });
      healthyHtml = `<div class="org-summary">${Object.entries(byOrg).map(([o, n]) => `<span>${esc(o)} · <b>${n}</b> healthy</span>`).join("")}</div>`;
    } else {
      healthyHtml = `<div class="healthy">${healthy.map(h => `<div class="ok-tile"><div class="n"><i></i>${esc(h.name)}</div><div class="o">${esc(h.org)}</div></div>`).join("")}</div>`;
    }

    document.getElementById("screen").innerHTML = `
    ${header(D)}
    ${pillar("hardware", "Hardware failures")}
    ${pillar("backup", "Backups")}
    ${pillar("antivirus", "Antivirus threats")}
    <div class="card online">
      <div class="label">Online now</div>
      ${[["Servers", D.online.servers], ["Workstations", D.online.workstations]].map(([k, v]) => `
        <div class="orow"><span class="k">${k}</span><span class="v">${v[0]}<small>/ ${v[1]}</small></span>
          <div class="meter"><div style="width:${v[1] ? v[0] / v[1] * 100 : 0}%"></div></div></div>`).join("")}
    </div>

    <section class="card servers${dense ? " dense" : ""}">
      <div class="card-head"><div class="card-title">Servers</div>
        <div class="card-sub">${affected.length ? `${affected.length} need attention · ` : ""}${healthy.length} healthy</div></div>
      ${affected.length
        ? `<div class="affected">${shownCards.map(srvCard).join("")}${hiddenCards > 0 ? `<div class="srv-card more-card">+${hiddenCards} more ${plural(hiddenCards, "server")}</div>` : ""}</div>`
        : `<div class="all-clear">${BIG_OK}<div><div class="t">All ${serversTotal} servers healthy</div><div class="m">No hardware, backup or antivirus issues on any server.</div></div></div>`}
      ${healthy.length ? `<div class="section-label"><i></i>Healthy · ${healthy.length} ${plural(healthy.length, "server")}</div>${healthyHtml}` : ""}
    </section>

    <section class="card clients">
      <div class="card-head"><div class="card-title">Workstations needing attention</div>
        <div class="card-sub">${D.workstationTotal > ws.length ? `worst ${ws.length} of ${D.workstationTotal}` : `${ws.length} of ${wsTotal}`}</div></div>
      ${ws.length ? `<div class="list">${ws.map(w => `
        <div class="item"><div class="sev ${w.severity}">${(CAT[w.category] || CAT.other)(16)}</div>
          <div style="min-width:0"><div class="t">${esc(w.text)}</div><div class="m"><span class="sevword">${WORD[w.severity] || ""}</span> · ${CATNAME[w.category] || ""} · ${esc(w.device)}${w.org ? " · " + esc(w.org) : ""}</div></div>
          <div class="ago">${ago(w.since)}</div></div>`).join("")}</div>`
        : `<div class="all-clear">${BIG_OK}<div><div class="t">No workstation issues</div><div class="m">${wsTotal} workstations checked.</div></div></div>`}
    </section>

    <section class="card trend">
      <div class="card-head"><div class="card-title">New incidents · last 14 days</div><div class="card-sub">today highlighted</div></div>
      <div class="rows">${["hardware", "backup", "antivirus"].map(k => `
        <div class="trow"><span class="k">${CAT[k](16)}${CATNAME[k]}</span>
          <div class="spark" data-k="${k}" style="height:62px"></div>
          <span class="tot">${sum(D.trend[k])}<small>14 days</small></span></div>`).join("")}</div>
    </section>`;

    const hEl = document.querySelector(".healthy");
    if (hEl && healthy.length) {
      const cols = dense ? 9 : 8, rows = Math.ceil(healthy.length / cols);
      const rowH = Math.max(28, Math.min(64, Math.floor((hEl.clientHeight - (rows - 1) * 8) / rows)));
      hEl.style.gridAutoRows = rowH + "px";
      hEl.classList.toggle("compact", rowH < 44);
    }
    document.querySelectorAll(".spark").forEach(el => { el.innerHTML = columns(D.trend[el.dataset.k] || [], el.clientWidth || 300, 62); });
    previousCritical = crit.size ? crit : new Set(["-"]);
    tick();
  }

  function header(D) {
    const orgs = D && D.orgCount ? `${D.orgCount} ${plural(D.orgCount, "organisation")} · ` : "";
    const counts = D && D.online ? `${D.online.servers[1]} servers · ${D.online.workstations[1]} workstations` : "NinjaOne";
    return `<header>
      <div class="brand">
        <div class="logo"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="9" rx="2"/><rect x="14" y="3" width="7" height="5" rx="2"/><rect x="14" y="12" width="7" height="9" rx="2"/><rect x="3" y="16" width="7" height="5" rx="2"/></svg></div>
        <div><div class="h">Infrastructure health</div><div class="s">${orgs}${counts}</div></div>
      </div>
      <div class="header-right">
        <div class="pill" id="status"><span class="dot"></span><span class="txt"></span></div>
        <div class="clock"><div class="time" id="clock-time"></div><div class="date" id="clock-date"></div></div>
      </div>
    </header>`;
  }

  async function load() {
    try {
      const r = await fetch("/api/summary", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      data = await r.json();
      fetchError = null;
      render();
    } catch (e) {
      fetchError = "Dashboard service not reachable";
      tick();
    }
  }

  // Screen on/off from Home Assistant: checked every 3 s so the black overlay follows quickly.
  function applyScreen(s) { document.documentElement.classList.toggle("screen-off", !!s && s.on === false); }
  async function pollScreen() {
    try {
      const r = await fetch("/api/screen", { cache: "no-store" });
      if (r.ok) applyScreen(await r.json());
    } catch (e) { /* keep the current state */ }
  }
  setInterval(pollScreen, 3000);

  fit();
  if (window.NINJADASH_INITIAL) applyScreen(window.NINJADASH_INITIAL.screen);
  if (window.NINJADASH_INITIAL) {
    data = window.NINJADASH_INITIAL;
    applyTheme();
    render();
  } else {
    applyTheme();
    load();
  }
  setInterval(load, REFRESH_MS);
  setInterval(tick, 1000);
  // A full reload once a day picks up new versions and keeps the browser fresh.
  setTimeout(() => location.reload(), 24 * 3600 * 1000);
})();
