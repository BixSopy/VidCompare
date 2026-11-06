/* VidCompare — interface. Affiche l'état renvoyé par le moteur Python et lui envoie les actions.
   Tous les textes viennent du catalogue de la langue active (T("clé")), chargé depuis le moteur. */
(function () {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const tier = (s) => (s >= 90 ? "var(--s1)" : s >= 75 ? "var(--s2)" : s >= 55 ? "var(--s3)" : s >= 35 ? "var(--s4)" : "var(--s5)");

  /* ---------- traductions ---------- */
  let STR = {}, STR_LANG = "";
  const T = (key, params) => {
    let s = STR[key];
    if (s == null) return key;
    if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (params[k] == null ? m : params[k]));
    return s;
  };
  const fmt = (n, d = 1) => Number(n).toFixed(d).replace(".", T("meta.decimal") === "meta.decimal" ? "." : T("meta.decimal"));
  async function loadStrings() {
    const r = await call("get_strings");
    if (r && r.strings) {
      STR = r.strings; STR_LANG = r.lang;
      document.documentElement.lang = r.lang; document.documentElement.dir = r.rtl ? "rtl" : "ltr";
    }
  }

  const ICON = {
    compare: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="8" height="14" rx="2.5"/><rect x="13" y="5" width="8" height="14" rx="2.5"/><path d="M7 12h0M17 12h0" stroke-width="3"/></svg>',
    library: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/></svg>',
    history: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3.5 4.5v4.2h4.2"/><path d="M12 7.5V12l3 2"/></svg>',
    settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2.2"/><circle cx="9" cy="17" r="2.2"/></svg>',
    chev: '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
    film: '<svg viewBox="0 0 24 24" width="38" height="38" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--faint)"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M8 4v16M16 4v16M3 9h5M3 15h5M16 9h5M16 15h5"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  };
  const NAV = ["compare", "library", "history", "settings"];

  const ui = { view: "compare", lib: "rank", open: {}, animate: true, lastKey: "" };
  let S = null;            // dernier état reçu du moteur

  /* ---------- liaison avec le moteur ---------- */
  async function call(name, ...args) {
    try {
      let out;
      if (window.pywebview && window.pywebview.api) out = await window.pywebview.api[name](...args);
      else {
        const r = await fetch("/api/" + name, { method: "POST", body: JSON.stringify(args) });
        out = await r.json();
      }
      if (out && out.error) { toast(out.error); return null; }
      return out;
    } catch (e) { toast(T("ui.engine_down")); return null; }
  }
  async function act(name, ...args) {
    const s = await call(name, ...args);
    if (s && s.slots) { if (s.lang !== STR_LANG) await loadStrings(); setState(s); }
    return s;
  }

  let lastSig = "";
  function setState(s) {
    if (s.toast) toast(s.toast);
    // Rien n'a changé (cas du rafraîchissement automatique) : on ne redessine pas la page.
    const { toast: _t, ...rest } = s, sig = JSON.stringify(rest);
    if (S && sig === lastSig) return;
    lastSig = sig;
    const main = $("#main"), top = main ? main.scrollTop : 0;
    S = s;
    const key = s.result ? JSON.stringify([s.result.total, s.slots.A && s.slots.A.name, s.slots.B && s.slots.B.name]) : "";
    if (key !== ui.lastKey) { ui.lastKey = key; ui.animate = true; }
    render();
    if (main && !ui.animate) main.scrollTop = top;
    ui.animate = false;
  }
  window.VC = { setState };

  /* ---------- petites briques ---------- */
  let toastTimer;
  function toast(msg) {
    let el = $("#toast");
    if (!el) { el = document.createElement("div"); el.id = "toast"; el.className = "toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
    el.textContent = msg; el.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 6000);
  }
  function modal({ title, hint = "", body, ok = T("ui.ok"), onOk, wide = false }) {
    const back = document.createElement("div"), opener = document.activeElement, id = "m" + Date.now();
    back.className = "modal-back";
    back.innerHTML = `<div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-labelledby="${id}-t" ${hint ? `aria-describedby="${id}-h"` : ""}>
      <h2 class="section-title" id="${id}-t">${esc(title)}</h2>${hint ? `<p class="section-sub" id="${id}-h">${esc(hint)}</p>` : ""}
      <div class="modal-body">${body}</div>
      <div class="modal-actions"><button class="btn" data-m="cancel">${esc(T("ui.cancel"))}</button><button class="btn primary" data-m="ok">${esc(ok)}</button></div></div>`;
    document.body.appendChild(back);
    // Le reste de la page devient inerte : le clavier et les lecteurs d'écran restent dans la fenêtre.
    const app = $(".app"); if (app) app.setAttribute("inert", "");
    const close = () => {
      back.remove();
      if (!$(".modal-back") && app) app.removeAttribute("inert");
      if (opener && opener.isConnected && opener.focus) opener.focus();     // le focus revient au bouton d'origine
    };
    back._close = close;
    back.addEventListener("click", (e) => { if (e.target === back || e.target.dataset.m === "cancel") close(); });
    $('[data-m="ok"]', back).addEventListener("click", async () => { if ((await onOk(back)) !== false) close(); });
    const first = $("textarea, input", back) || $('[data-m="ok"]', back); first.focus();
    return back;
  }
  const textModal = (title, hint, placeholder, ok, onOk, multiline = false) => modal({
    title, hint, ok, onOk: (b) => { const v = $("#m-text", b).value.trim(); return v ? onOk(v) : false; },
    wide: multiline, body: multiline ? `<textarea id="m-text" class="field-text" rows="12" placeholder="${esc(placeholder)}"></textarea>` : `<input id="m-text" class="field-text" placeholder="${esc(placeholder)}">`,
  });
  const inApp = () => !!(window.pywebview && window.pywebview.api);

  function ring(score, cls = "ring", r = 44, sw = 7) {
    const C = 2 * Math.PI * r, off = C * (1 - (score || 0) / 100);
    return `<div class="${cls}"><svg viewBox="0 0 100 100" aria-hidden="true"><circle class="track" cx="50" cy="50" r="${r}" fill="none" stroke-width="${sw}"/>
      <circle class="value" cx="50" cy="50" r="${r}" fill="none" stroke-width="${sw}" stroke="${tier(score)}" stroke-dasharray="${C}"
        stroke-dashoffset="${ui.animate ? C : off}" data-offset="${off}"/></svg>
      <div class="${cls === "ring" ? "ring-num" : "num"}" style="color:${tier(score)}">${score == null ? "—" : fmt(score)}</div></div>`;
  }
  const chips = (list, cls = "") => `<div class="chips">${list.map((c) => `<span class="chip ${cls}">${esc(c)}</span>`).join("")}</div>`;
  const head = (title, sub) => `<header class="page-head"><h1 class="page-title">${esc(title)}</h1><p class="page-sub">${esc(sub)}</p></header>`;
  const spinner = (txt) => `<span class="spin-line"><i class="spin"></i>${esc(txt)}</span>`;
  const btn = (act, label, extra = "", cls = "") => `<button class="btn ${cls}" data-act="${act}" ${extra}>${esc(label)}</button>`;

  /* ---------- Comparer ---------- */
  function slot(tag) {
    const d = S.slots[tag];
    const label = `<div class="slot-head"><div class="slot-tag"><span class="slot-letter">${tag}</span><span class="slot-label">${esc(T("ui.file_n", { tag }))}</span></div>`;
    if (!d) {
      return `<section class="card slot" data-slot="${tag}">${label}</div>
        <div class="drop">${ICON.film}
          <div><p class="drop-title">${esc(T("ui.drop_title"))}</p><p>${esc(T("ui.drop_sub"))}</p></div>
          <div class="drop-actions">${btn("pick-video", T("ui.pick_video"), `data-tag="${tag}"`, "primary")}${btn("pick-torrent", T("ui.pick_torrent"), `data-tag="${tag}"`)}</div>
          <div class="link-actions"><button class="link-btn" data-act="magnet" data-tag="${tag}">${esc(T("ui.paste_magnet"))}</button>
            <button class="link-btn" data-act="report" data-tag="${tag}">${esc(T("ui.paste_report"))}</button></div></div></section>`;
    }
    const st = d.status === "ready" ? `<span class="status"><i class="dot ok"></i><span>${esc(T("ui.ready"))}</span></span>`
      : d.status === "loading" ? `<span class="status">${spinner(T("ui.analyzing"))}</span>`
      : `<span class="status"><i class="dot bad"></i><span>${esc(T("ui.error"))}</span></span>`;
    return `<section class="card slot" data-slot="${tag}">${label}${st}</div>
      <div><h2 class="file-name">${esc(d.name)}</h2><p class="file-meta" style="margin-top:8px">${esc(d.kind)}${d.size ? " · " + esc(d.size) : ""}</p>
        ${d.status === "error" ? `<p class="file-meta err" style="margin-top:8px">${esc(d.note)}</p>` : d.note ? `<p class="file-meta" style="margin-top:8px">${esc(d.note)}</p>` : ""}</div>
      ${chips(d.chips)}
      <div class="slot-actions">${btn("pick-video", T("ui.change"), `data-tag="${tag}"`, "small")}${btn("clear", T("ui.remove"), `data-tag="${tag}"`, "small danger")}</div></section>`;
  }
  const who = (x) => (x > 0 ? "A" : "B");
  function critRow(x) {
    const adv = Math.abs(x.adv) < 0.05 ? `<span class="adv zero">${esc(T("ui.equal"))}</span>` : `<span class="adv ${x.adv < 0 ? "b" : ""}">${who(x.adv)} +${fmt(Math.abs(x.adv))}</span>`;
    if (x.a[1] == null || x.b[1] == null) {
      return `<div class="crit-row"><div class="crit-name">${esc(x.key)}</div><div class="bars"><span>A : ${esc(x.a[0])}</span><span>B : ${esc(x.b[0])}</span></div>${adv}</div>`;
    }
    const line = (tag, [val, sc], win) => `<div class="bar-line ${win ? "" : "lose"}"><span class="bar-tag">${tag}</span>
      <div class="track"><div class="fill" style="background:${tier(sc)};width:${ui.animate ? 0 : sc}%" data-w="${sc}"></div></div>
      <div class="bar-val"><span>${esc(val)}</span><span class="num">${sc}</span></div></div>`;
    return `<div class="crit-row"><div class="crit-name">${esc(x.key)}</div>
      <div class="bars">${line("A", x.a, x.a[1] >= x.b[1])}${line("B", x.b, x.b[1] >= x.a[1])}</div>${adv}</div>`;
  }
  const fold = (id, title, hint, body) => `<details class="fold" data-fold="${id}" ${ui.open[id] ? "open" : ""}><summary><span>${esc(title)}<span class="hint">${esc(hint)}</span></span>${ICON.chev}</summary><div class="fold-body">${body}</div></details>`;
  function visualBlock(r) {
    const v = r.visual, on = v.available && !v.busy ? "" : "disabled";
    return `<p class="section-sub" style="margin-bottom:18px">${esc(v.hint)}</p>
      <div class="visual-actions">${btn("frames", T("ui.frames"), on)}${btn("vmaf", T("ui.vmaf"), `title="${esc(T("ui.vmaf_tip"))}" ${on}`)}</div>
      ${v.text ? `<div class="visual-result ${v.error ? "err" : ""}">${v.busy ? spinner(v.text) : esc(v.text)}</div>` : ""}`;
  }
  function result() {
    const r = S.result, w = r.winner;
    const sc = (tag) => `<div class="score ${w !== tag && w !== "égalité" ? "dim" : ""}"><div class="score-tag">${w === tag ? esc(T("ui.best")) : "&nbsp;"}</div>
        ${ring(r.total[tag])}<div class="score-name" title="${esc(S.slots[tag].name)}">${esc(T("ui.file_n", { tag }))}</div></div>`;
    const title = w === "égalité" ? T("ui.tie_title") : T("ui.better_title", { tag: w });
    const alertCount = r.alerts.A.length + r.alerts.B.length;
    const alerts = ["A", "B"].map((tag) => `<p class="sub-h">${esc(T("ui.file_n", { tag }))}</p><ul class="alert-list">${r.alerts[tag].length ? r.alerts[tag].map((a) => `<li><span class="sev ${a.level}">${esc(T("sev." + a.level))}</span><span>${esc(a.text)}</span></li>`).join("") : `<li><span class='sev info'>${esc(T("ui.nothing"))}</span><span>${esc(T("ui.nothing_to_report"))}</span></li>`}</ul>
      ${r.tracks[tag].length ? `<ul class="alert-list">${r.tracks[tag].map((x) => `<li><span class="sev info">${esc(T("ui.track"))}</span><span>${esc(x)}</span></li>`).join("")}</ul>` : ""}`).join("");
    const table = `<table class="t"><thead><tr><th>${esc(T("ui.criterion"))}</th><th>${esc(T("ui.file_n", { tag: "A" }))}</th><th>${esc(T("ui.score"))}</th><th>${esc(T("ui.file_n", { tag: "B" }))}</th><th>${esc(T("ui.score"))}</th></tr></thead><tbody>
      ${r.rows.map((x) => `<tr><td>${esc(x.key)}</td><td>${esc(x.a[0])}</td><td class="sc" style="color:${tier(x.a[1])}">${x.a[1] == null ? "" : x.a[1]}</td><td>${esc(x.b[0])}</td><td class="sc" style="color:${tier(x.b[1])}">${x.b[1] == null ? "" : x.b[1]}</td></tr>`).join("")}
      <tr><td><b>${esc(T("ui.total_score"))}</b></td><td></td><td class="sc" style="color:${tier(r.total.A)}">${fmt(r.total.A)}</td><td></td><td class="sc" style="color:${tier(r.total.B)}">${fmt(r.total.B)}</td></tr></tbody></table>`;
    return `
    <section class="section" style="margin-top:36px"><div class="card hero" data-winner="${w}">${sc("A")}
      <div class="verdict"><div class="verdict-kicker">${esc(T("ui.verdict"))}</div><div class="verdict-title">${esc(title)}</div>
        <div class="verdict-gap">${w === "égalité" ? "" : "+"}${fmt(r.gap)}<small>${esc(T("ui.points"))}</small></div>
        ${r.sizeNote ? `<p class="verdict-note">${esc(r.sizeNote)}</p>` : ""}</div>${sc("B")}</div>
      ${r.versions.length ? `<div class="notice ${r.versionsBlock ? "alert" : ""}" role="note"><div class="notice-title">${esc(T(r.versionsBlock ? "ui.versions_title_block" : "ui.versions_title"))}</div>
        <ul>${r.versions.map((x) => `<li>${esc(x.text)}</li>`).join("")}</ul></div>` : ""}
      ${r.partial ? `<p class="file-meta" style="margin-top:14px">${esc(T("ui.partial"))}</p>` : ""}</section>
    ${r.reasons.length ? `<section class="section"><h2 class="section-title">${esc(T("ui.reasons"))}</h2><p class="section-sub">${esc(T("ui.reasons_sub"))}</p>
      <div class="reasons">${r.reasons.map((x) => `<div class="card reason"><div class="reason-top"><span class="reason-label">${esc(x.label)}</span><span class="reason-pts ${x.who === "B" ? "b" : ""}">${x.who} +${fmt(x.points)}</span></div><p>${esc(x.text)}</p></div>`).join("")}</div></section>` : ""}
    <section class="section"><h2 class="section-title">${esc(T("ui.by_criterion"))}</h2><p class="section-sub">${esc(T("ui.by_criterion_sub"))}</p><div class="card crit">${r.rows.map(critRow).join("")}</div></section>
    <section class="section">
      ${fold("table", T("ui.fold_table"), T("ui.fold_table_hint"), table)}
      ${fold("why", T("ui.fold_why"), T("ui.fold_why_hint"), `<ul class="alert-list">${r.why.map((x) => `<li style="grid-template-columns:1fr">${esc(x)}</li>`).join("")}</ul>`)}
      ${fold("alerts", T("ui.fold_alerts"), T("ui.alerts_count", { n: alertCount }), alerts)}
      ${fold("visual", T("ui.fold_visual"), T("ui.fold_visual_hint"), visualBlock(r))}
    </section>
    <div class="row-between" style="margin-top:28px"><span class="file-meta">${esc(T("ui.saved_in_history"))}</span>${btn("save-report", T("ui.save_report"))}</div>`;
  }
  function compareView() {
    const both = S.slots.A && S.slots.B;
    let tail;
    if (S.result) tail = result();
    else if (both) tail = `<p class="file-meta" style="margin-top:28px">${spinner(T("ui.analyzing_dots"))}</p>`;
    else tail = `<p class="file-meta" style="margin-top:28px">${esc(T(S.slots.A || S.slots.B ? "ui.one_missing" : "ui.no_comparison"))}</p>`;
    return `<div class="page">${head(T("ui.compare_title"), T("ui.compare_sub"))}<div class="slots">${slot("A")}${slot("B")}</div>${tail}</div>`;
  }

  /* ---------- Bibliothèque ---------- */
  function ranking() {
    const R = S.ranking;
    const row = (x) => x.status !== "ready"
      ? `<div class="card item"><div class="item-rank">·</div><div><h3 class="item-title">${esc(x.name)}</h3><p class="item-meta">${esc(x.kind)}</p>${x.status === "error" ? `<p class="file-meta err">${esc(x.note)}</p>` : spinner(T("ui.analyzing"))}</div>
          <div class="row-actions">${btn("rank-remove", T("ui.remove"), `data-id="${x.id}"`, "small danger")}</div></div>`
      : `<div class="card item"><div class="item-rank">${x.rank}</div>
          <div><h3 class="item-title">${esc(x.name)}</h3><p class="item-meta">${esc(x.kind)} · ${esc(x.size)}</p>
            <div class="chips">${x.chips.map((c) => `<span class="chip">${esc(c)}</span>`).join("")}${x.alerts ? `<span class="chip alert">${esc(T("ui.alerts_n", { n: x.alerts }))}</span>` : ""}</div>
            <div class="row-actions" style="margin-top:14px">${btn("rank-send", T("ui.send_a"), `data-id="${x.id}" data-tag="A"`, "small")}${btn("rank-send", T("ui.send_b"), `data-id="${x.id}" data-tag="B"`, "small")}${btn("rank-remove", T("ui.remove"), `data-id="${x.id}"`, "small danger")}</div></div>
          ${ring(x.score, "mini-ring", 44, 9)}</div>`;
    return `<div class="toolbar" style="margin-top:0">${btn("rank-pick", T("ui.add_videos"), `data-v="videos"`, "primary small").replace(">" + esc(T("ui.add_videos")), ">" + ICON.plus + esc(T("ui.add_videos")))}
      ${btn("rank-pick", T("ui.add_folder"), `data-v="folder"`, "small")}${btn("rank-pick", T("ui.add_torrents"), `data-v="torrents"`, "small")}
      ${btn("rank-magnet", T("ui.add_magnet"), "", "small")}<span style="flex:1"></span>
      ${btn("rank-export", T("ui.export_csv"), "", "small")}${btn("rank-clear", T("ui.clear"), "", "small danger")}</div>
      ${R.rows.length ? `<div class="list">${R.rows.map(row).join("")}</div>` : `<div class="card empty"><p class="drop-title">${esc(T("ui.rank_empty_title"))}</p><p>${esc(T("ui.rank_empty"))}</p></div>`}
      ${R.estimated ? `<p class="file-meta" style="margin-top:18px">${esc(T("ui.rank_estimated"))}</p>` : ""}`;
  }
  function upgrades() {
    const L = S.library;
    const card = (x) => `<div class="card up-item"><div><h3 class="up-title">${esc(x.title)}</h3>${chips(x.fix)}</div>
      <div class="gainbar"><div class="gain-num"><span>${fmt(x.now)} → ${fmt(x.target)}</span><span class="big">+${fmt(x.gain)}</span></div>
        <div class="track"><div class="ghost" style="width:${x.target}%"></div><div class="now" style="width:${x.now}%;background:${tier(x.now)}"></div></div>
        <span class="file-meta">${esc(x.size)}</span></div></div>`;
    const more = (kind, left) => (left > 0 ? `<div style="margin-top:16px;text-align:center">${btn("up-more", T("ui.show_more", { n: left }), `data-kind="${kind}"`)}</div>` : "");
    const none = `<div class="card empty"><p>${esc(T("ui.nothing_to_improve"))}</p></div>`;
    const scan = L.scan ? `<div class="banner" style="display:block"><div class="row-between"><span>${spinner(T("ui.scan_progress", { done: L.scan.done, total: L.scan.total }) + (L.scan.cached ? " " + T("ui.scan_cached", { n: L.scan.cached }) : ""))}</span>${btn("up-cancel", T("ui.cancel"), "", "small")}</div>
      <div class="track" style="margin-top:12px"><div class="fill" style="width:${L.scan.total ? (100 * L.scan.done) / L.scan.total : 0}%;background:var(--accent)"></div></div></div>` : "";
    return `<div class="folders">${L.folders.map((f) => `<span class="folder">${esc(f)}<button aria-label="${esc(T("ui.remove"))} ${esc(f)}" data-act="up-remove" data-path="${esc(f)}">×</button></span>`).join("")}
        <button class="btn small" data-act="up-add">${ICON.plus}${esc(T("ui.add_folder_btn"))}</button></div>
      <div class="toolbar"><label class="file-meta" for="lvl">${esc(T("ui.aim"))}</label>
        <select class="sel" id="lvl" data-act="up-level">${L.levels.map(([id, label]) => `<option value="${esc(id)}" ${id === L.level ? "selected" : ""}>${esc(label)}</option>`).join("")}</select>
        ${btn("up-scan", T("ui.scan_folders"), L.scan ? "disabled" : "", "primary")}</div>
      <div class="banner"><b>${esc(T("ui.aim_label"))}</b><span>${esc(L.wanted)}</span>${L.summary ? `<span class="file-meta">· ${esc(L.summary)}</span>` : ""}</div>${scan}
      ${L.hasResults ? `<div class="section" style="margin-top:36px"><h2 class="section-title">${esc(T("ui.films_title"))} <span class="file-meta">(${L.filmsTotal})</span></h2>
        <p class="section-sub">${esc(T("ui.films_sub"))}</p><div class="list">${L.films.map(card).join("") || none}</div>${more("films", L.filmsTotal - L.films.length)}</div>
        <div class="section" style="margin-top:40px"><h2 class="section-title">${esc(T("ui.series_title"))} <span class="file-meta">(${esc(T("ui.seasons_n", { n: L.seriesTotal }))})</span></h2>
        <p class="section-sub">${esc(T("ui.series_sub"))}</p><div class="list">${L.series.map(card).join("") || none}</div>${more("series", L.seriesTotal - L.series.length)}</div>
        <div style="margin-top:24px">${btn("up-export", T("ui.export_list"), "", "small")}</div>`
      : `<div class="card empty" style="margin-top:28px"><p class="drop-title">${esc(T("ui.no_scan_title"))}</p><p>${esc(T("ui.no_scan"))}</p></div>`}`;
  }
  function libraryView() {
    const seg = `<div class="seg" role="group"><button aria-pressed="${ui.lib === "rank"}" data-act="lib" data-v="rank">${esc(T("ui.tab_rank"))}</button><button aria-pressed="${ui.lib === "up"}" data-act="lib" data-v="up">${esc(T("ui.tab_upgrades"))}</button></div>`;
    return `<div class="page">${head(T("ui.library_title"), T("ui.library_sub"))}<div style="margin-bottom:28px">${seg}</div>${ui.lib === "rank" ? ranking() : upgrades()}</div>`;
  }

  /* ---------- Historique ---------- */
  function historyView() {
    const H = S.history;
    return `<div class="page">${head(T("ui.history_title"), T("ui.history_sub"))}
      <div class="toolbar" style="margin-top:0">${btn("hist-export", T("ui.export_csv"), "", "small")}${btn("hist-clear", T("ui.clear_all"), "", "small danger")}</div>
      ${H.length ? `<div class="list">${H.map((h) => `<div class="card hist"><div class="hist-date">${esc(h.date)}</div>
        ${["a", "b"].map((k, i) => { const sc = h["s" + k]; return `<div class="hist-side ${h.winner === "AB"[i] ? "win" : ""}"><div class="n" title="${esc(h[k])}">${esc(h[k])}</div><div class="s" style="color:${tier(sc)}">${fmt(sc)}</div></div>`; }).join("")}
        <div class="hist-actions">${btn("hist-open", T("ui.reopen"), `data-id="${h.id}"`, "small")}${btn("hist-remove", T("ui.delete"), `data-id="${h.id}"`, "small danger")}</div></div>`).join("")}</div>`
      : `<div class="card empty"><p class="drop-title">${esc(T("ui.history_empty_title"))}</p><p>${esc(T("ui.history_empty"))}</p></div>`}</div>`;
  }

  /* ---------- Réglages ---------- */
  function settingsView() {
    const s = S.settings;
    const segOf = (items, cur, act) => `<div class="seg" role="group">${items.map(([v, l]) => `<button aria-pressed="${v === cur}" data-act="${act}" data-v="${esc(v)}">${esc(l)}</button>`).join("")}</div>`;
    const sel = (items, cur, act, label) => `<select class="sel" data-act="${act}" aria-label="${esc(label)}">${items.map(([v, l]) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
    const same = (arr) => arr.map((x) => [x, x]);
    return `<div class="page">${head(T("ui.settings_title"), T("ui.settings_sub"))}
      <div class="grid2">
        <section class="card panel"><h3>${esc(T("ui.set_ui_lang"))}</h3><p class="hint">${esc(T("ui.set_ui_lang_hint"))}</p>${sel(s.uiLangs, s.uiLang, "ui-lang", T("ui.set_ui_lang"))}</section>
        <section class="card panel"><h3>${esc(T("ui.set_theme"))}</h3><p class="hint">${esc(T("ui.set_theme_hint"))}</p>${segOf([["cinema", T("ui.theme_cinema")], ["oled", T("ui.theme_oled")]], S.theme, "theme-set")}</section>
        <section class="card panel" style="grid-column:1/-1"><h3>${esc(T("ui.set_content_lang"))}</h3><p class="hint">${esc(T("ui.set_content_lang_hint"))}</p>
          <div class="stack">${segOf(s.langs, s.lang, "lang-set")}${sel(s.contentLangs, s.contentLang, "content-lang", T("ui.set_content_lang"))}</div></section>
        <section class="card panel" style="grid-column:1/-1"><h3>${esc(T("ui.set_weights"))}</h3><p class="hint">${esc(T("ui.set_weights_hint"))}</p>
          ${segOf(s.profiles, s.profile, "profile-set")}
          <div class="sliders">${s.weights.map(([k, l, v]) => `<div class="slider-row"><span>${esc(l)}</span><input type="range" min="0" max="40" value="${v}" data-act="weight" data-key="${k}" aria-label="${esc(l)}"><span class="num">${v}</span></div>`).join("")}</div></section>
        <section class="card panel"><h3>${esc(T("ui.set_device"))}</h3><p class="hint">${esc(T("ui.set_device_hint"))}</p>
          <div class="stack">${sel(s.presets, s.preset, "preset", T("ui.set_device"))}</div>
          <div class="switches" style="margin-top:20px">${s.device.map(([k, l, on]) => `<label class="switch"><span>${esc(l)}</span><span class="sw"><input type="checkbox" data-act="device" data-key="${k}" ${on ? "checked" : ""}><span></span></span></label>`).join("")}</div>
          <div class="field" style="margin-top:22px"><span>${esc(T("ui.max_res"))}</span>${segOf(same(["2160p", "1080p"]), s.maxRes, "maxres")}</div></section>
        <section class="card panel"><h3>${esc(T("ui.set_torrents"))}</h3><p class="hint">${esc(T("ui.set_torrents_hint"))}</p>
          <div class="field"><span>${esc(T("ui.duration"))}</span><div class="stepper"><button data-act="runtime" data-d="-10" aria-label="${esc(T("ui.less"))}">−</button><span class="num">${esc(T("unit.min", { n: s.runtime }))}</span><button data-act="runtime" data-d="10" aria-label="${esc(T("ui.more"))}">+</button></div></div>
          ${S.ffmpeg.ok ? "" : `<div class="field" style="margin-top:22px"><span>${esc(T("ui.ffprobe_missing"))}</span>${btn("pick-ffprobe", T("ui.pick_ffprobe"), "", "small")}</div>`}</section>
        <section class="card panel" style="grid-column:1/-1"><h3>${esc(T("ui.set_update"))}</h3><p class="hint">${esc(T("ui.set_update_hint"))}</p>
          <div class="row-between"><label class="switch"><span>${esc(T("ui.update_auto"))}</span><span class="sw"><input type="checkbox" data-act="update-auto" ${S.updateCheck ? "checked" : ""}><span></span></span></label>
          ${btn("update-check", T("ui.update_check"), "", "small")}</div></section>
        <section class="card panel" style="grid-column:1/-1"><div class="row-between"><div><h3>${esc(T("ui.diag"))}</h3><p class="hint" style="margin-bottom:0">${esc(T("ui.diag_hint", { version: S.version }))}</p></div>
          ${btn("open-log", T("ui.open_log"), "", "small")}</div></section>
        <section class="card panel" style="grid-column:1/-1"><div class="row-between"><div><h3>${esc(T("ui.set_groups"))}</h3><p class="hint" style="margin-bottom:0">${esc(T("ui.set_groups_hint"))}</p></div>
          <button class="btn small" data-act="group-add">${ICON.plus}${esc(T("ui.add_group"))}</button></div>
          <div style="margin-top:14px">${s.groups.length ? s.groups.map(([g, v]) => `<div class="group-row"><span>${esc(g)}</span><span class="row-actions"><span class="stepper small"><button data-act="group-step" data-name="${esc(g)}" data-v="${v}" data-d="-1" aria-label="${esc(T("ui.less"))}">−</button><span class="num ${v >= 0 ? "pos" : "neg"}">${v > 0 ? "+" : ""}${v}</span><button data-act="group-step" data-name="${esc(g)}" data-v="${v}" data-d="1" aria-label="${esc(T("ui.more"))}">+</button></span>${btn("group-remove", T("ui.remove"), `data-name="${esc(g)}"`, "small danger")}</span></div>`).join("") : `<p class="file-meta">${esc(T("ui.no_groups"))}</p>`}</div></section>
      </div></div>`;
  }

  /* ---------- rendu ---------- */
  const VIEWS = { compare: compareView, library: libraryView, history: historyView, settings: settingsView };
  function render() {
    if (!S) return;
    document.body.dataset.theme = S.theme === "oled" ? "oled" : "cinema";
    document.title = "VidCompare";
    $("#nav").innerHTML = NAV.map((id) => `<button data-act="nav" data-v="${id}" ${ui.view === id ? 'aria-current="page"' : ""}>${ICON[id]}<span>${esc(T("nav." + id))}</span></button>`).join("");
    $("#theme-seg").setAttribute("aria-label", T("ui.set_theme"));
    $("#theme-seg").innerHTML =[["cinema", T("ui.theme_cinema")], ["oled", T("ui.theme_oled")]].map(([v, l]) => `<button aria-pressed="${v === S.theme}" data-act="theme-set" data-v="${v}">${esc(l)}</button>`).join("");
    $("#version").textContent = T("ui.version", { version: S.version });
    $("#ffmpeg-status").innerHTML = S.ffmpeg.ok ? `<i class="dot ok"></i><span>${esc(T("ui.ffmpeg_ready"))}</span>` : `<i class="dot bad"></i><span>${esc(T("ui.ffmpeg_missing"))}</span>`;
    const banner = S.ffmpeg.ok ? "" : `<div class="warn-banner"><span>${esc(T("ui.ffmpeg_banner"))}</span>${btn("pick-ffprobe", T("ui.pick_ffprobe"), "", "small")}</div>`;
    const main = $("#main");
    const upd = S.update ? `<div class="warn-banner upd"><span>${esc(T("ui.update_banner", { version: S.update.version }))}</span>${btn("update-open", T("ui.update_get"), "", "small")}</div>` : "";
    main.innerHTML = banner + upd + VIEWS[ui.view]();
    if (ui.animate) requestAnimationFrame(() => requestAnimationFrame(() => {
      $$(".ring .value, .mini-ring .value", main).forEach((c) => (c.style.strokeDashoffset = c.dataset.offset));
      $$(".fill[data-w]", main).forEach((f) => (f.style.width = f.dataset.w + "%"));
    }));
  }

  /* ---------- actions ---------- */
  const ask = {
    magnet: (cb) => textModal(T("ui.magnet_title"), T("ui.magnet_hint"), "magnet:?xt=urn:btih:…&dn=…", T("ui.add"), cb),
    path: (what, cb) => textModal(what, T("ui.dev_path_hint"), "C:\\Films\\Film.mkv", T("ui.ok"), cb),
  };
  async function openFrames() {
    const r = await call("show_frames");
    if (!r || !r.ok) { toast((r && r.error) || T("ui.frames_unavailable")); return; }
    let i = 0;
    const m = modal({ title: T("ui.frames_title"), hint: `A : ${r.nameA}   ·   B : ${r.nameB}`, ok: T("ui.close"), wide: true, onOk: () => true,
      body: `${(r.warnings || []).map((w) => `<p class="file-meta ${w.level === "alert" ? "err" : ""}">${esc(w.text)}</p>`).join("")}<div class="gallery"><img alt="${esc(T("ui.frames_alt"))}"><div class="gallery-nav"><button class="btn small" data-g="-1">‹ ${esc(T("ui.prev"))}</button><span class="file-meta" id="g-cap"></span><button class="btn small" data-g="1">${esc(T("ui.next"))} ›</button></div><p class="file-meta">${esc(T("ui.frames_hdr"))}</p></div>` });
    $('[data-m="cancel"]', m).remove();
    const show = () => { $("img", m).src = r.frames[i].src; const sec = r.frames[i].t; $("#g-cap", m).textContent = T("ui.frame_caption", { i: i + 1, n: r.frames.length, m: Math.floor(sec / 60), s: String(sec % 60).padStart(2, "0") }); };
    m.addEventListener("click", (e) => { const g = e.target.closest("[data-g]"); if (g) { i = (i + Number(g.dataset.g) + r.frames.length) % r.frames.length; show(); } });
    show();
  }
  document.addEventListener("click", async (e) => {
    const el = e.target.closest("[data-act]");
    if (!el || el.tagName === "SELECT" || el.tagName === "INPUT") return;
    const a = el.dataset.act, d = el.dataset, tag = d.tag;
    if (a === "nav") { ui.view = d.v; ui.animate = true; render(); ui.animate = false; $("#main").scrollTop = 0; return; }
    if (a === "lib") { ui.lib = d.v; ui.animate = true; render(); ui.animate = false; return; }
    if (a === "pick-video") return inApp() ? act("pick_video", tag) : ask.path(T("ui.path_video"), (v) => act("set_source", tag, v));
    if (a === "pick-torrent") return inApp() ? act("pick_torrent", tag) : ask.path(T("ui.path_torrent"), (v) => act("set_source", tag, v));
    if (a === "magnet") return ask.magnet((v) => act("set_source", tag, v));
    if (a === "report") return textModal(T("ui.report_title"), T("ui.report_hint"), "General\nComplete name : …\n\nVideo\nFormat : HEVC\n…", T("ui.report_ok"), (v) => act("set_report", tag, v), true);
    if (a === "clear") return act("clear_slot", tag);
    if (a === "frames") return openFrames();
    if (a === "vmaf") {
      const bad = S.result.versions.find((x) => x.level === "alert");
      if (!bad) return act("run_vmaf");
      return modal({ title: T("ui.vmaf_confirm_title"), hint: bad.text, ok: T("ui.vmaf_confirm_ok"),
        body: `<p class="file-meta">${esc(T("ui.vmaf_confirm_body"))}</p>`, onOk: () => act("run_vmaf") });
    }
    if (a === "up-more") return act("up_more", d.kind);
    if (a === "open-log") return act("open_log_folder");
    if (a === "update-check") return act("check_update");
    if (a === "update-open") return act("open_update_page");
    if (a === "save-report") return act("save_report");
    if (a === "rank-pick") return inApp() ? act("rank_pick", d.v) : ask.path(T("ui.path_any"), (v) => act("rank_add", [v]));
    if (a === "rank-magnet") return ask.magnet((v) => act("rank_add_magnet", v));
    if (a === "rank-remove") return act("rank_remove", Number(d.id));
    if (a === "rank-send") { await act("rank_send", Number(d.id), tag); ui.view = "compare"; render(); return; }
    if (a === "rank-clear") return act("rank_clear");
    if (a === "rank-export") return act("rank_export");
    if (a === "up-add") return inApp() ? act("up_add_folder") : ask.path(T("ui.path_folder"), (v) => act("up_add_folder", v));
    if (a === "up-remove") return act("up_remove_folder", d.path);
    if (a === "up-scan") return act("up_scan");
    if (a === "up-cancel") return act("up_cancel");
    if (a === "up-export") return act("up_export");
    if (a === "hist-open") { await act("hist_reopen", Number(d.id)); ui.view = "compare"; render(); return; }
    if (a === "hist-remove") return act("hist_remove", Number(d.id));
    if (a === "hist-clear") return modal({ title: T("ui.clear_all_title"), hint: T("ui.clear_all_hint"), ok: T("ui.clear_all_ok"), body: "", onOk: () => act("hist_clear") });
    if (a === "hist-export") return act("hist_export");
    if (a === "theme-set") return act("set_theme", d.v);
    if (a === "lang-set") return act("set_lang", d.v);
    if (a === "profile-set") return act("set_profile", d.v);
    if (a === "maxres") return act("set_max_res", d.v);
    if (a === "runtime") return act("set_runtime", S.settings.runtime + Number(d.d));
    if (a === "pick-ffprobe") return act("pick_ffprobe");
    if (a === "group-add") return modal({ title: T("ui.group_title"), hint: T("ui.group_hint"), ok: T("ui.add"),
      body: `<input id="g-name" class="field-text" placeholder="${esc(T("ui.group_placeholder"))}"><label class="file-meta" for="g-bonus" style="display:block;margin:14px 0 6px">${esc(T("ui.group_bonus"))}</label><input id="g-bonus" class="field-text" type="number" min="-10" max="10" step="1" value="0">`,
      onOk: (b) => { const n = $("#g-name", b).value.trim(); if (!n) return false; return act("group_set", n, Number($("#g-bonus", b).value || 0)); } });
    if (a === "group-step") return act("group_set", d.name, Math.max(-10, Math.min(10, Number(d.v) + Number(d.d))));
    if (a === "group-remove") return act("group_remove", d.name);
  });
  document.addEventListener("change", (e) => {
    const el = e.target, a = el.dataset && el.dataset.act;
    if (!a) return;
    if (a === "weight") act("set_weight", el.dataset.key, Number(el.value));
    else if (a === "device") act("set_device", el.dataset.key, el.checked);
    else if (a === "update-auto") act("set_update_check", el.checked);
    else if (a === "preset") act("set_preset", el.value);
    else if (a === "up-level") act("up_set_level", el.value);
    else if (a === "ui-lang") act("set_ui_lang", el.value);
    else if (a === "content-lang") act("set_content_lang", el.value);
  });
  document.addEventListener("input", (e) => { if (e.target.type === "range" && e.target.dataset.act) e.target.parentElement.querySelector(".num").textContent = e.target.value; });
  document.addEventListener("toggle", (e) => { const f = e.target.dataset && e.target.dataset.fold; if (f) ui.open[f] = e.target.open; }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { const m = $(".modal-back"); if (m && m._close) m._close(); } });

  /* ---------- glisser-déposer ---------- */
  const pathOf = (f) => f.pywebviewFullPath || f.path || "";
  ["dragenter", "dragover"].forEach((n) => document.addEventListener(n, (e) => { e.preventDefault(); const s = e.target.closest && e.target.closest("[data-slot]"); $$("[data-slot]").forEach((x) => x.classList.toggle("over", x === s)); }));
  document.addEventListener("dragleave", (e) => { if (!e.relatedTarget) $$("[data-slot]").forEach((x) => x.classList.remove("over")); });
  document.addEventListener("drop", async (e) => {
    e.preventDefault();
    $$("[data-slot]").forEach((x) => x.classList.remove("over"));
    const files = [...(e.dataTransfer.files || [])], paths = files.map(pathOf).filter(Boolean);
    const text = (e.dataTransfer.getData("text") || "").trim();
    const sources = paths.length ? paths : text.startsWith("magnet:") ? [text] : [];
    if (!sources.length) { if (files.length) toast(T("ui.drop_no_path")); return; }
    if (ui.view === "library" && ui.lib === "rank") return act("rank_add", sources);
    if (ui.view === "library") { for (const p of sources) await act("up_add_folder", p); return; }
    if (ui.view !== "compare") return;
    const over = e.target.closest && e.target.closest("[data-slot]");
    for (const src of sources.slice(0, 2)) {
      const free = over && sources.length === 1 ? over.dataset.slot : !S.slots.A ? "A" : !S.slots.B ? "B" : "B";
      await act("set_source", free, src);
    }
  });

  /* ---------- démarrage ---------- */
  async function boot() {
    await loadStrings();
    const s = await call("get_state");
    if (s && s.slots) { setState(s); return; }
    $("#main").innerHTML = `<div class="page"><h1 class="page-title">${esc(T("ui.engine_down_title"))}</h1><p class="page-sub">${esc(T("ui.engine_down_sub"))}</p></div>`;
  }
  let started = false;
  const start = () => { if (!started) { started = true; boot(); } };
  window.addEventListener("pywebviewready", start);
  setTimeout(() => { if (!window.pywebview) start(); }, 500);       // mode développement : pas de pywebview
  if (window.pywebview && window.pywebview.api) start();
  // Tant qu'une analyse tourne en arrière-plan, on redemande l'état : filet si une notification est perdue,
  // et seul moyen de se tenir à jour en mode navigateur (sans fenêtre pywebview pour pousser l'état).
  const working = () => !!S && (["A", "B"].some((tag) => S.slots[tag] && S.slots[tag].status === "loading") ||
    S.ranking.rows.some((r) => r.status === "loading") || !!S.library.scan || (S.result && S.result.visual.busy));
  setInterval(() => { if (working() && !document.querySelector(".modal-back")) call("get_state").then((s) => s && s.slots && setState(s)); }, 800);
})();
