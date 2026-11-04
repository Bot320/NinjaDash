/* NinjaDash wall display: fetches /api/summary every 30 s, draws the 1920x1080 screen, and
   shrinks long lists to what fits ("+N more") so nothing is cut off. */
(function () {
  "use strict";
  const REFRESH_MS = 30000;

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = n => Number(n || 0).toLocaleString("en-US");
  const svg = (p, s = 16) => `<svg width="${s}" height="${s}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
  const CAT = {
    hardware:  s => svg('<rect x="2" y="3.5" width="12" height="9" rx="2"/><path d="M2 9h12"/><circle cx="11.3" cy="11" r=".6" fill="currentColor"/>', s),
    backup:    s => svg('<path d="M13.2 8.4A5.2 5.2 0 1 1 11.7 4.3"/><path d="M12.4 1.8v2.9H9.5"/><path d="M8 5.5V8l1.7 1.2"/>', s),
    antivirus: s => svg('<path d="M8 1.8 13.2 3.7v3.9c0 3-2.2 5.3-5.2 6.6-3-1.3-5.2-3.6-5.2-6.6V3.7z"/><path d="M5.8 8l1.5 1.5 2.9-3"/>', s),
    offline:   s => svg('<path d="M8 1.8v5.4"/><path d="M4.4 4.3a5.2 5.2 0 1 0 7.2 0"/>', s),
    other:     s => svg('<circle cx="8" cy="8" r="6.2"/><path d="M8 4.8v3.6"/><circle cx="8" cy="11" r=".6" fill="currentColor"/>', s),
    patch:     s => svg('<rect x="2.2" y="2.2" width="11.6" height="11.6" rx="2.5"/><path d="M8 5v5.2"/><path d="M5.6 7.9 8 10.3l2.4-2.4"/>', s),
    apps:      s => svg('<rect x="2.2" y="2.2" width="4.8" height="4.8" rx="1.2"/><rect x="9" y="2.2" width="4.8" height="4.8" rx="1.2"/><rect x="2.2" y="9" width="4.8" height="4.8" rx="1.2"/><path d="M11.4 9.2v4.4M9.2 11.4h4.4"/>', s),
    storage:   s => svg('<ellipse cx="8" cy="3.8" rx="5.6" ry="2"/><path d="M2.4 3.8v8.4c0 1.1 2.5 2 5.6 2s5.6-.9 5.6-2V3.8"/><path d="M2.4 8c0 1.1 2.5 2 5.6 2s5.6-.9 5.6-2"/>', s)
  };
  const CATNAME = { hardware: "Hardware", backup: "Backup", antivirus: "Antivirus", offline: "Offline", other: "Other" };
  const SEV = {
    critical: '<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor"/><rect x="7" y="3.6" width="2" height="5.6" rx="1" fill="#fff"/><circle cx="8" cy="11.6" r="1.1" fill="#fff"/></svg>',
    warning:  '<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.8 14.6 13.6H1.4z" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><rect x="7.1" y="5.6" width="1.8" height="4.4" rx=".9" fill="#fff"/><circle cx="8" cy="11.8" r=".95" fill="#fff"/></svg>',
    ok:       '<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor"/><path d="M5 8.2l2 2 4-4.2" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    offline:  '<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M5 8h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
  };
  const ICON = { clock: svg('<circle cx="8" cy="8" r="6.2"/><path d="M8 4.6V8l2.3 1.5"/>', 12) };
  const dayLabel = epoch => new Date(epoch * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const BIG_OK = SEV.ok.replace('width="14" height="14"', 'width="28" height="28"');
  const WORD = { critical: "Critical", warning: "Warning", ok: "All clear", offline: "Offline", minor: "Minor" };
  const STATEVAR = { critical: "var(--critical)", warning: "var(--warning)", ok: "var(--good)", offline: "var(--offline)" };
  const plural = (n, w) => (n === 1 ? w : w + "s");
  const chip = s => `<span class="chip ${s}"><span class="ic">${SEV[s] || SEV.warning}</span>${WORD[s] || s}</span>`;
  const sum = a => (a || []).reduce((x, y) => x + y, 0);

  let data = null, fetchError = null, previousCritical = new Set(), loadedVersion = null;

  function ago(epoch) {
    if (!epoch) return "";
    const s = Math.max(0, Date.now() / 1000 - epoch);
    if (s < 60) return "now";
    if (s < 3600) return Math.floor(s / 60) + " min";
    if (s < 48 * 3600) return Math.floor(s / 3600) + " h";
    return Math.floor(s / 86400) + " d";
  }
  function bytes(b) {
    if (!b && b !== 0) return "";
    const gb = b / 1024 ** 3;
    return gb >= 1000 ? (gb / 1024).toFixed(1) + " TB" : gb >= 10 ? Math.round(gb) + " GB" : gb.toFixed(1) + " GB";
  }
  const sevDot = s => (/critical/i.test(s || "") ? "critical" : /important|high/i.test(s || "") ? "warning" : "");
  const issueText = i => (i.category === "offline" ? "Not responding" : i.text);

  // ---- theme (time of day or Home Assistant, decided by the backend) and screen on/off ----
  function applyTheme(effective) {
    const mode = effective === "light" ? "light" : "dark";
    if (document.documentElement.dataset.theme !== mode) document.documentElement.dataset.theme = mode;
  }
  function applyScreen(s) {
    if (!s) return;
    document.documentElement.classList.toggle("screen-off", s.on === false);
    if (s.theme) applyTheme(s.theme);
  }
  async function pollScreen() {
    try {
      const r = await fetch("/api/screen", { cache: "no-store" });
      if (r.ok) applyScreen(await r.json());
    } catch (e) { /* keep the current state */ }
  }

  // ---- scale the 1920x1080 canvas to the screen ----
  function fit() {
    const scale = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
    document.getElementById("screen").style.transform = `scale(${scale})`;
  }
  window.addEventListener("resize", fit);

  // ---- status pill + clock ----
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
    if (p) { const s = statusPill(); p.className = "pill " + s.cls; p.querySelector(".txt").textContent = s.text; }
  }

  // ---- dynamic fitting: hide trailing items until the box no longer overflows ----
  const overflows = el => el.scrollHeight > el.clientHeight + 1;
  function fitItems(box, items, onHidden) {
    let hidden = 0;
    for (let i = items.length - 1; i >= 0 && overflows(box); i--) {
      items[i].style.display = "none";
      hidden++;
      if (onHidden) onHidden(hidden);
    }
    return hidden;
  }

  // ---- drawing ----
  function columns(values, w, h) {
    const n = values.length, slot = w / n, bw = Math.min(14, slot - 6), top = 16, base = h - 2;
    const max = Math.max(4, ...values), y = v => base - v / max * (base - top);
    let s = `<svg width="${w}" height="${h}" aria-hidden="true"><line x1="0" x2="${w}" y1="${base}" y2="${base}" stroke="var(--axis)"/>`;
    values.forEach((v, i) => {
      const x0 = slot * i + (slot - bw) / 2, last = i === n - 1;
      const fill = last ? "var(--accent)" : "color-mix(in srgb, var(--accent) 42%, transparent)";
      if (v > 0) {
        const y1 = y(v), r = Math.min(3, (base - y1) / 2);
        s += `<path d="M${x0},${base} V${y1 + r} Q${x0},${y1} ${x0 + r},${y1} H${x0 + bw - r} Q${x0 + bw},${y1} ${x0 + bw},${y1 + r} V${base} Z" fill="${fill}"/>`;
      }
      if (last) s += `<text x="${x0 + bw / 2}" y="${y(v) - 4}" text-anchor="middle" fill="var(--text-1)" style="font-size:12px;font-weight:700;font-family:inherit">${v}</text>`;
    });
    return s + "</svg>";
  }

  function header(D) {
    const parts = [];
    if (D && D.orgCount) parts.push(`<b>${fmt(D.orgCount)}</b> ${plural(D.orgCount, "organisation")}`);
    if (D && D.online) {
      parts.push(`<b>${fmt(D.online.servers[1])}</b> ${plural(D.online.servers[1], "server")}`);
      parts.push(`<b>${fmt(D.online.workstations[1])}</b> ${plural(D.online.workstations[1], "workstation")}`);
    }
    return `<header>
      <div class="fleet">${parts.join('<span class="sep">·</span>') || "NinjaDash"}</div>
      <div class="header-right">
        <div class="pill" id="status"><span class="dot"></span><span class="txt"></span></div>
        <div class="clock"><div class="time" id="clock-time"></div><div class="date" id="clock-date"></div></div>
      </div>
    </header>`;
  }

  function pillar(D, key, label) {
    const p = (D.pillars || {})[key] || { servers: 0, workstations: 0, state: "ok", note: "" };
    const total = p.servers + p.workstations, state = total ? p.state : "ok";
    return `<div class="card pillar" style="--state:${STATEVAR[state] || STATEVAR.warning}">
      <div class="top"><div class="label">${CAT[key](18)}${label}</div>${chip(state)}</div>
      <div class="mid"><div class="value">${total}</div><div class="unit">${total === 1 ? "device" : "devices"} affected</div></div>
      <div class="split"><span class="srv"><b>${p.servers}</b> ${plural(p.servers, "server")}</span><span><b>${p.workstations}</b> ${plural(p.workstations, "workstation")}</span><span class="note">${esc(p.note)}</span></div>
    </div>`;
  }

  function serversCard(D) {
    const affected = D.affected || [], healthy = D.healthy || [];
    const total = (D.online && D.online.servers[1]) || 0;
    const isNew = s => previousCritical.size && s.state === "critical" && !previousCritical.has(s.org + "/" + s.name);
    // Every card carries up to 2 issues; fitServers() picks the layout (2 or 3 columns, 1 or 2 issues).
    const card = s => `<div class="srv-card${isNew(s) ? " flash" : ""}" style="--state:${STATEVAR[s.state] || STATEVAR.warning}" data-issues="${s.issues.length}">
        <div class="hd"><div><span class="nm">${esc(s.name)}</span><span class="org">${esc(s.org)}</span></div>${chip(s.state)}</div>
        ${s.issues.slice(0, 2).map((i, n) => `<div class="issue i${n + 1}">${(CAT[i.category] || CAT.other)(16)}<span>${esc(issueText(i))}</span><span class="since">${ago(i.since)}</span></div>`).join("")}
        <div class="more" style="display:none"></div>
      </div>`;
    const byOrg = {};
    healthy.forEach(h => { const o = h.org || "Other"; byOrg[o] = (byOrg[o] || 0) + 1; });
    const healthyLine = healthy.length ? `<div class="healthy-line"><span class="lbl"><i></i>Healthy</span>${Object.entries(byOrg)
      .map(([o, n]) => `<span class="org-chip">${esc(o)} <b>${n}</b></span>`).join("")}</div>` : "";
    return `<section class="card servers">
      <div class="card-head"><div class="card-title">Servers</div>
        <div class="card-sub">${affected.length ? `${affected.length} need attention · ` : ""}${healthy.length} healthy</div></div>
      <div class="srv-body fill">
        ${affected.length
          ? `<div class="affected">${affected.map(card).join("")}<div class="srv-card more-card" style="display:none"></div></div>`
          : `<div class="all-clear">${BIG_OK}<div><div class="t">All ${total} servers healthy</div><div class="m">No hardware, backup or antivirus issues on any server.</div></div></div>`}
        ${healthyLine}
      </div>
    </section>`;
  }

  // Windows update names are long; keep the part that tells them apart on a TV
  const compactName = n => String(n || "")
    .replace(/Cumulative Update/gi, "CU")
    .replace(/Servicing Stack Update/gi, "SSU")
    .replace(/\bfor Windows\b/gi, "Win")
    .replace(/\bfor Microsoft server operating system,? version\b/gi, "Server")
    .replace(/\.NET Framework/gi, ".NET")
    .replace(/\s+/g, " ").trim();

  function patchColumn(title, icon, u, emptyText) {
    if (!u) return `<div class="upd"><div class="uh">${icon}${title}</div><div class="na">Not available from NinjaOne for this account.</div></div>`;
    // "20/40 approved": 20 devices already approved, 20 still waiting (40 need the update)
    const split = t => `${fmt(t.approved)}/${fmt(t.approved + t.devices)} approved${t.servers ? `<span class="ok"> · ${fmt(t.servers)} srv</span>` : ""}`;
    const count = t => t.servers && t.servers === t.devices ? `${fmt(t.servers)} ${plural(t.servers, "server")}`
      : `${fmt(t.devices)} ${plural(t.devices, "device")}${t.servers ? ` · ${fmt(t.servers)} srv` : ""}`;
    const rows = (u.top || []).map(t => `<div class="urow"><span class="dot ${sevDot(t.severity)}"></span><span class="nm">${esc(compactName(t.name))}</span>
        <span class="ct">${t.approved ? split(t) : count(t)}${t.auto ? ` · auto ${dayLabel(t.auto)}` : ""}</span></div>`).join("");
    const meta = [`on <b>${fmt(u.approvalDevices)}</b> ${plural(u.approvalDevices, "device")}`];
    if (u.approvalServers) meta.push(`<b>${fmt(u.approvalServers)}</b> ${plural(u.approvalServers, "server")}`);
    const onDev = n => n == null ? "" : ` on ${fmt(n)} ${plural(n, "device")}`;
    const meta2 = [`<b>${fmt(u.queued)}</b> approved${onDev(u.queuedDevices)}`];
    if (u.failed) meta2.push(`<b>${fmt(u.failed)}</b> failed`);
    const meta3 = !u.autoApprove ? "" : `<div class="meta m2">${ICON.clock}<b>${fmt(u.autoApprove)}</b> auto-approve · next ${dayLabel(u.autoApproveNext)}</div>`;
    return `<div class="upd"><div class="uh">${icon}${title}</div>
      <div class="big"><span class="n">${fmt(u.approval)}</span><span class="u">awaiting approval</span></div>
      <div class="meta">${meta.join(" · ")}</div>
      <div class="meta m2">${meta2.join(" · ")}</div>${meta3}
      <div class="rows">${rows || `<div class="more-line">${emptyText}</div>`}<div class="more-line" style="display:none"></div></div>
    </div>`;
  }

  function storageColumn(st) {
    if (!st) return `<div class="upd"><div class="uh">${CAT.storage(16)}Low storage</div><div class="na">Not available from NinjaOne for this account.</div></div>`;
    const rows = (st.items || []).map(i => `<div class="srow">
        <span class="nm">${esc(i.device)} · ${esc(i.volume)}<small>${esc(bytes(i.free))} free</small></span>
        <span class="pct">${Math.round(i.usedPct)} %</span>
        <div class="bar"><div class="${i.severity}" style="width:${Math.min(100, i.usedPct)}%"></div></div></div>`).join("");
    const meta = st.total ? `<b>${st.servers}</b> on ${plural(st.servers, "server")} · <b>${st.critical}</b> critical (≥ 95 %)` : "every volume has enough free space";
    return `<div class="upd"><div class="uh">${CAT.storage(16)}Low storage</div>
      <div class="big"><span class="n">${fmt(st.total)}</span><span class="u">${plural(st.total, "volume")} ≥ ${Math.round(st.warnPercent || 90)} % full</span></div>
      <div class="meta">${meta}</div>
      <div class="rows">${rows}<div class="more-line" style="display:none"></div></div>
    </div>`;
  }

  function render() {
    const D = data;
    const screen = document.getElementById("screen");
    if (!D || !D.ready) {
      screen.innerHTML = header(D) + `<div class="boot">${esc(D && D.error ? D.error : "Loading data from NinjaOne…")}</div>`;
      tick();
      return;
    }
    if (D.theme) applyTheme(D.theme.effective);
    const ws = D.workstations || [];
    const wsTotal = (D.online && D.online.workstations[1]) || 0;
    const up = D.updates || {};

    screen.innerHTML = `
    ${header(D)}
    ${pillar(D, "hardware", "Hardware failures")}
    ${pillar(D, "backup", "Backups")}
    ${pillar(D, "antivirus", "Antivirus threats")}
    <div class="card online">
      <div class="label">Online now</div>
      ${[["Servers", D.online.servers], ["Workstations", D.online.workstations]].map(([k, v]) => `
        <div class="orow"><span class="k">${k}</span><span class="v">${fmt(v[0])}<small>/ ${fmt(v[1])}</small></span>
          <div class="meter"><div style="width:${v[1] ? v[0] / v[1] * 100 : 0}%"></div></div></div>`).join("")}
    </div>

    ${serversCard(D)}

    <section class="card clients">
      <div class="card-head"><div class="card-title">Workstations needing attention</div><div class="card-sub" id="ws-sub"></div></div>
      ${ws.length ? `<div class="list fill">${ws.map(w => `
        <div class="item"><div class="sev ${w.severity}">${(CAT[w.category] || CAT.other)(16)}</div>
          <div style="min-width:0"><div class="t">${esc(w.text)}</div><div class="m"><span class="sevword">${WORD[w.severity] || ""}</span> · ${CATNAME[w.category] || ""} · ${esc(w.device)}${w.org ? " · " + esc(w.org) : ""}</div></div>
          <div class="since">${ago(w.since)}</div></div>`).join("")}</div>`
        : `<div class="all-clear">${BIG_OK}<div><div class="t">No workstation issues</div><div class="m">${fmt(wsTotal)} workstations checked.</div></div></div>`}
    </section>

    <section class="card updates">
      <div class="card-head"><div class="card-title">Updates &amp; storage</div><div class="card-sub">waiting for approval in NinjaOne</div></div>
      <div class="upd-grid fill">
        ${patchColumn("OS patches", CAT.patch(16), up.os, "No OS patches waiting for approval.")}
        ${patchColumn("App updates", CAT.apps(16), up.apps, "No app updates waiting for approval.")}
        ${storageColumn(up.storage)}
      </div>
    </section>

    <section class="card trend">
      <div class="card-head"><div class="card-title">New incidents · last 14 days</div><div class="card-sub">today highlighted</div></div>
      <div class="trows fill">${["hardware", "backup", "antivirus"].map(k => `
        <div class="trow"><span class="k">${CAT[k](16)}${CATNAME[k]}</span>
          <div class="spark" data-k="${k}" style="height:58px"></div>
          <span class="tot">${sum(D.trend[k])}<small>14 days</small></span></div>`).join("")}</div>
    </section>`;

    fitAll(D);
    document.querySelectorAll(".spark").forEach(el => { el.innerHTML = columns(D.trend[el.dataset.k] || [], el.clientWidth || 300, 58); });
    const crit = new Set((D.affected || []).filter(s => s.state === "critical").map(s => s.org + "/" + s.name));
    previousCritical = crit.size ? crit : new Set(["-"]);
    tick();
  }

  function fitAll(D) {
    fitServers();
    // Workstations: show as many as fit.
    const list = document.querySelector(".clients .list");
    const ws = D.workstations || [], total = D.workstationTotal || ws.length;
    const wsTotal = (D.online && D.online.workstations[1]) || 0;
    let shown = ws.length;
    if (list) shown -= fitItems(list, [...list.children]);
    const sub = document.getElementById("ws-sub");
    if (sub) sub.textContent = total > shown ? `worst ${shown} of ${fmt(total)}` : `${fmt(shown)} of ${fmt(wsTotal)}`;
    // Updates & storage: each column shows as many rows as fit.
    document.querySelectorAll(".upd .rows").forEach(rows => {
      const more = rows.querySelector(".more-line[style]");
      const items = [...rows.children].filter(c => c !== more && !c.classList.contains("more-line"));
      if (!more || !items.length || !overflows(rows)) return;
      more.style.display = "";
      const hidden = fitItems(rows, items, n => { more.textContent = `+${n} more`; });
      if (!hidden) more.style.display = "none";
    });
  }

  // Servers: try the most detailed layout first and step down until everything fits:
  // 2 columns with 2 issues each → 3 columns → 3 columns with 1 issue → "+N more servers".
  // The "healthy" line is dropped before detail is lost. Cards are sorted worst first.
  function fitServers() {
    const body = document.querySelector(".srv-body");
    if (!body) return;
    const line = body.querySelector(".healthy-line");
    const grid = body.querySelector(".affected");
    if (!grid) { if (line && overflows(body)) line.style.display = "none"; return; }
    const cards = [...grid.querySelectorAll(".srv-card:not(.more-card)")];
    const setMore = perCard => cards.forEach(c => {
      const extra = Number(c.dataset.issues) - perCard, m = c.querySelector(".more");
      m.style.display = extra > 0 ? "" : "none";
      m.textContent = extra > 0 ? `+${extra} more ${plural(extra, "issue")}` : "";
    });
    const layouts = [{ cols3: false, one: false }, { cols3: true, one: false }, { cols3: true, one: true }];
    for (const l of layouts) {
      grid.classList.toggle("cols-3", l.cols3);
      grid.classList.toggle("one", l.one);
      setMore(l.one ? 1 : 2);
      if (line) line.style.display = "";
      if (!overflows(body)) return;
      if (line) line.style.display = "none";
      if (!overflows(body)) return;
    }
    const more = grid.querySelector(".more-card");
    more.style.display = "";
    const hidden = fitItems(body, cards, n => { more.textContent = `+${n} more ${plural(n, "server")}`; });
    if (!hidden) more.style.display = "none";
  }

  async function load() {
    try {
      const r = await fetch("/api/summary", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      data = await r.json();
      fetchError = null;
      if (loadedVersion && data.version && data.version !== loadedVersion) { location.reload(); return; }
      loadedVersion = loadedVersion || data.version;
      render();
      applyScreen(data.screen);
    } catch (e) {
      fetchError = "Dashboard service not reachable";
      tick();
    }
  }

  fit();
  if (window.NINJADASH_INITIAL) {
    data = window.NINJADASH_INITIAL;
    loadedVersion = data.version;
    applyScreen(data.screen);
    render();
  } else {
    load();
  }
  if (document.fonts) document.fonts.ready.then(() => { if (data) render(); });
  setInterval(load, REFRESH_MS);
  setInterval(pollScreen, 3000);
  setInterval(tick, 1000);

  // Never let the screen time out: a wake lock tells the compositor (cage) not to go idle.
  // The kiosk has no screensaver anyway; this is belt and braces. Switching off is done by NinjaDash.
  let wakeLock = null;
  async function keepAwake() {
    try {
      if (navigator.wakeLock && !wakeLock && document.visibilityState === "visible") {
        wakeLock = await navigator.wakeLock.request("screen");
        wakeLock.addEventListener("release", () => { wakeLock = null; });
      }
    } catch (e) { /* not supported or refused: nothing else to do */ }
  }
  document.addEventListener("visibilitychange", keepAwake);
  setInterval(keepAwake, 60000);
  keepAwake();
})();
