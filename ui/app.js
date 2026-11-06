/* VidCompare — interface. Affiche l'état renvoyé par le moteur Python et lui envoie les actions. */
(function () {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (n, d = 1) => Number(n).toFixed(d).replace(".", ",");
  const tier = (s) => (s >= 90 ? "var(--s1)" : s >= 75 ? "var(--s2)" : s >= 55 ? "var(--s3)" : s >= 35 ? "var(--s4)" : "var(--s5)");

  const ICON = {
    compare: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="8" height="14" rx="2.5"/><rect x="13" y="5" width="8" height="14" rx="2.5"/><path d="M7 12h0M17 12h0" stroke-width="3"/></svg>',
    library: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/></svg>',
    history: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3.5 4.5v4.2h4.2"/><path d="M12 7.5V12l3 2"/></svg>',
    settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2.2"/><circle cx="9" cy="17" r="2.2"/></svg>',
    chev: '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
    film: '<svg viewBox="0 0 24 24" width="38" height="38" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--faint)"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M8 4v16M16 4v16M3 9h5M3 15h5M16 9h5M16 15h5"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  };
  const NAV = [["compare", "Comparer"], ["library", "Bibliothèque"], ["history", "Historique"], ["settings", "Réglages"]];

  const ui = { view: "compare", lib: "rank", open: {}, animate: true, lastKey: "" };
  let S = null;            // dernier état reçu du moteur
  let backendOk = true;

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
      backendOk = true;
      return out;
    } catch (e) { backendOk = false; toast("Le moteur ne répond pas."); return null; }
  }
  async function act(name, ...args) { const s = await call(name, ...args); if (s && s.slots) setState(s); return s; }

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
    let t = $("#toast");
    if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
    t.textContent = msg; t.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 6000);
  }
  function modal({ title, hint = "", body, ok = "Valider", onOk, wide = false }) {
    const back = document.createElement("div"), opener = document.activeElement, id = "m" + Date.now();
    back.className = "modal-back";
    back.innerHTML = `<div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-labelledby="${id}-t" ${hint ? `aria-describedby="${id}-h"` : ""}>
      <h2 class="section-title" id="${id}-t">${esc(title)}</h2>${hint ? `<p class="section-sub" id="${id}-h">${esc(hint)}</p>` : ""}
      <div class="modal-body">${body}</div>
      <div class="modal-actions"><button class="btn" data-m="cancel">Annuler</button><button class="btn primary" data-m="ok">${esc(ok)}</button></div></div>`;
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
  const head = (title, sub) => `<header class="page-head"><h1 class="page-title">${title}</h1><p class="page-sub">${sub}</p></header>`;
  const spinner = (txt) => `<span class="spin-line"><i class="spin"></i>${esc(txt)}</span>`;

  /* ---------- Comparer ---------- */
  function slot(tag) {
    const d = S.slots[tag];
    const label = `<div class="slot-head"><div class="slot-tag"><span class="slot-letter">${tag}</span><span class="slot-label">Fichier ${tag}</span></div>`;
    if (!d) {
      return `<section class="card slot" data-slot="${tag}">${label}</div>
        <div class="drop">${ICON.film}
          <div><p class="drop-title">Déposez un fichier ici</p><p>Une vidéo, un fichier .torrent ou un lien magnet</p></div>
          <div class="drop-actions"><button class="btn primary" data-act="pick-video" data-tag="${tag}">Choisir une vidéo</button>
            <button class="btn" data-act="pick-torrent" data-tag="${tag}">Choisir un .torrent</button></div>
          <div class="link-actions"><button class="link-btn" data-act="magnet" data-tag="${tag}">Coller un magnet</button>
            <button class="link-btn" data-act="report" data-tag="${tag}">Coller un rapport MediaInfo</button></div></div></section>`;
    }
    const st = d.status === "ready" ? `<span class="status"><i class="dot ok"></i><span>Prêt</span></span>`
      : d.status === "loading" ? `<span class="status">${spinner("Analyse en cours")}</span>`
      : `<span class="status"><i class="dot bad"></i><span>Erreur</span></span>`;
    return `<section class="card slot" data-slot="${tag}">${label}${st}</div>
      <div><h2 class="file-name">${esc(d.name)}</h2><p class="file-meta" style="margin-top:8px">${esc(d.kind)}${d.size ? " · " + esc(d.size) : ""}</p>
        ${d.status === "error" ? `<p class="file-meta err" style="margin-top:8px">${esc(d.note)}</p>` : d.note ? `<p class="file-meta" style="margin-top:8px">${esc(d.note)}</p>` : ""}</div>
      ${chips(d.chips)}
      <div class="slot-actions"><button class="btn small" data-act="pick-video" data-tag="${tag}">Changer</button>
        <button class="btn small danger" data-act="clear" data-tag="${tag}">Retirer</button></div></section>`;
  }
  const who = (x) => (x > 0 ? "A" : "B");
  function critRow(x) {
    const adv = Math.abs(x.adv) < 0.05 ? `<span class="adv zero">égal</span>` : `<span class="adv ${x.adv < 0 ? "b" : ""}">${who(x.adv)} +${fmt(Math.abs(x.adv))}</span>`;
    if (x.a[1] == null || x.b[1] == null) {
      return `<div class="crit-row"><div class="crit-name">${esc(x.key)}</div><div class="bars"><span>A : ${esc(x.a[0])}</span><span>B : ${esc(x.b[0])}</span></div>${adv}</div>`;
    }
    const line = (tag, [val, sc], win) => `<div class="bar-line ${win ? "" : "lose"}"><span class="bar-tag">${tag}</span>
      <div class="track"><div class="fill" style="background:${tier(sc)};width:${ui.animate ? 0 : sc}%" data-w="${sc}"></div></div>
      <div class="bar-val"><span>${esc(val)}</span><span class="num">${sc}</span></div></div>`;
    return `<div class="crit-row"><div class="crit-name">${esc(x.key)}</div>
      <div class="bars">${line("A", x.a, x.a[1] >= x.b[1])}${line("B", x.b, x.b[1] >= x.a[1])}</div>${adv}</div>`;
  }
  const SEV = { alert: "Alerte", warn: "Attention", info: "Info" };
  const fold = (id, title, hint, body) => `<details class="fold" data-fold="${id}" ${ui.open[id] ? "open" : ""}><summary><span>${title}<span class="hint">${hint}</span></span>${ICON.chev}</summary><div class="fold-body">${body}</div></details>`;
  function visualBlock(r) {
    const v = r.visual;
    return `<p class="section-sub" style="margin-bottom:18px">${esc(v.hint)}</p>
      <div class="visual-actions"><button class="btn" data-act="frames" ${v.available && !v.busy ? "" : "disabled"}>Voir les images côte à côte</button>
        <button class="btn" data-act="vmaf" title="VMAF : mesure de Netflix qui note de 0 à 100 à quel point une vidéo ressemble à une autre" ${v.available && !v.busy ? "" : "disabled"}>Mesurer la ressemblance (VMAF)</button></div>
      ${v.text ? `<div class="visual-result ${v.error ? "err" : ""}">${v.busy ? spinner(v.text) : esc(v.text)}</div>` : ""}`;
  }
  function result() {
    const r = S.result, w = r.winner;
    const nm = (t) => S.slots[t].name;
    const sc = (tag) => `<div class="score ${w !== tag && w !== "égalité" ? "dim" : ""}"><div class="score-tag">${w === tag ? "Meilleure qualité" : "&nbsp;"}</div>
        ${ring(r.total[tag])}<div class="score-name" title="${esc(nm(tag))}">Fichier ${tag}</div></div>`;
    const title = w === "égalité" ? "Qualité équivalente" : `Le fichier ${w} est meilleur`;
    const alertCount = r.alerts.A.length + r.alerts.B.length;
    const alerts = ["A", "B"].map((t) => `<p class="sub-h">Fichier ${t}</p><ul class="alert-list">${r.alerts[t].length ? r.alerts[t].map((a) => `<li><span class="sev ${a.level}">${SEV[a.level]}</span><span>${esc(a.text)}</span></li>`).join("") : "<li><span class='sev info'>Rien</span><span>Rien à signaler.</span></li>"}</ul>
      ${r.tracks[t].length ? `<ul class="alert-list">${r.tracks[t].map((x) => `<li><span class="sev info">Piste</span><span>${esc(x)}</span></li>`).join("")}</ul>` : ""}`).join("");
    const table = `<table class="t"><thead><tr><th>Critère</th><th>Fichier A</th><th>Note</th><th>Fichier B</th><th>Note</th></tr></thead><tbody>
      ${r.rows.map((x) => `<tr><td>${esc(x.key)}</td><td>${esc(x.a[0])}</td><td class="sc" style="color:${tier(x.a[1])}">${x.a[1] == null ? "" : x.a[1]}</td><td>${esc(x.b[0])}</td><td class="sc" style="color:${tier(x.b[1])}">${x.b[1] == null ? "" : x.b[1]}</td></tr>`).join("")}
      <tr><td><b>Note totale</b></td><td></td><td class="sc" style="color:${tier(r.total.A)}">${fmt(r.total.A)}</td><td></td><td class="sc" style="color:${tier(r.total.B)}">${fmt(r.total.B)}</td></tr></tbody></table>`;
    return `
    <section class="section" style="margin-top:36px"><div class="card hero" data-winner="${w}">${sc("A")}
      <div class="verdict"><div class="verdict-kicker">Verdict</div><div class="verdict-title">${title}</div>
        <div class="verdict-gap">${w === "égalité" ? "" : "+"}${fmt(r.gap)}<small>points</small></div>
        ${r.sizeNote ? `<p class="verdict-note">${esc(r.sizeNote)}</p>` : ""}</div>${sc("B")}</div>
      ${r.versions.length ? `<div class="notice ${r.versionsBlock ? "alert" : ""}" role="note"><div class="notice-title">${r.versionsBlock ? "Ces deux fichiers ne semblent pas être le même montage" : "À savoir avant de comparer l'image"}</div>
        <ul>${r.versions.map((x) => `<li>${esc(x.text)}</li>`).join("")}</ul></div>` : ""}
      ${r.partial ? `<p class="file-meta" style="margin-top:14px">Comparaison partielle : certains critères n'ont pas pu être évalués pour les deux fichiers (torrent ou magnet estimé, rapport collé ou disque illisible).</p>` : ""}</section>
    ${r.reasons.length ? `<section class="section"><h2 class="section-title">Les raisons principales</h2><p class="section-sub">Ce qui pèse le plus dans l'écart.</p>
      <div class="reasons">${r.reasons.map((x) => `<div class="card reason"><div class="reason-top"><span class="reason-label">${esc(x.label)}</span><span class="reason-pts ${x.who === "B" ? "b" : ""}">${x.who} +${fmt(x.points)}</span></div><p>${esc(x.text)}</p></div>`).join("")}</div></section>` : ""}
    <section class="section"><h2 class="section-title">Critère par critère</h2><p class="section-sub">Chaque barre est une note sur 100.</p><div class="card crit">${r.rows.map(critRow).join("")}</div></section>
    <section class="section">
      ${fold("table", "Tableau complet", "toutes les valeurs et notes", table)}
      ${fold("why", "Explication détaillée", "points gagnés critère par critère", `<ul class="alert-list">${r.why.map((x) => `<li style="grid-template-columns:1fr">${esc(x)}</li>`).join("")}</ul>`)}
      ${fold("alerts", "Points d'attention", `${alertCount} signalement${alertCount > 1 ? "s" : ""}`, alerts)}
      ${fold("visual", "Comparer l'image", "images côte à côte et score VMAF", visualBlock(r))}
    </section>
    <div class="row-between" style="margin-top:28px"><span class="file-meta">Cette comparaison est gardée dans l'historique.</span><button class="btn" data-act="save-report">Enregistrer le rapport</button></div>`;
  }
  function compareView() {
    const both = S.slots.A && S.slots.B;
    let tail = "";
    if (S.result) tail = result();
    else if (both) tail = `<p class="file-meta" style="margin-top:28px">${spinner("Analyse en cours…")}</p>`;
    else tail = `<p class="file-meta" style="margin-top:28px">${S.slots.A || S.slots.B ? "Il manque encore un fichier." : "Aucune comparaison pour l'instant."}</p>`;
    return `<div class="page">${head("Comparer deux versions", "Mettez un fichier dans chaque case. Le résultat s'affiche juste en dessous.")}<div class="slots">${slot("A")}${slot("B")}</div>${tail}</div>`;
  }

  /* ---------- Bibliothèque ---------- */
  function ranking() {
    const R = S.ranking;
    const row = (x) => x.status !== "ready"
      ? `<div class="card item"><div class="item-rank">·</div><div><h3 class="item-title">${esc(x.name)}</h3><p class="item-meta">${esc(x.kind)}</p>${x.status === "error" ? `<p class="file-meta err">${esc(x.note)}</p>` : spinner("Analyse en cours")}</div>
          <div class="row-actions"><button class="btn small danger" data-act="rank-remove" data-id="${x.id}">Retirer</button></div></div>`
      : `<div class="card item"><div class="item-rank">${x.rank}</div>
          <div><h3 class="item-title">${esc(x.name)}</h3><p class="item-meta">${esc(x.kind)} · ${esc(x.size)}</p>
            <div class="chips">${x.chips.map((c) => `<span class="chip">${esc(c)}</span>`).join("")}${x.alerts ? `<span class="chip alert">${x.alerts} alerte${x.alerts > 1 ? "s" : ""}</span>` : ""}</div>
            <div class="row-actions" style="margin-top:14px"><button class="btn small" data-act="rank-send" data-id="${x.id}" data-tag="A">Envoyer en A</button><button class="btn small" data-act="rank-send" data-id="${x.id}" data-tag="B">Envoyer en B</button><button class="btn small danger" data-act="rank-remove" data-id="${x.id}">Retirer</button></div></div>
          ${ring(x.score, "mini-ring", 44, 9)}</div>`;
    return `<div class="toolbar" style="margin-top:0"><button class="btn primary small" data-act="rank-pick" data-v="videos">${ICON.plus}Des vidéos</button>
      <button class="btn small" data-act="rank-pick" data-v="folder">Un dossier</button><button class="btn small" data-act="rank-pick" data-v="torrents">Des torrents</button>
      <button class="btn small" data-act="rank-magnet">Un magnet</button><span style="flex:1"></span>
      <button class="btn small" data-act="rank-export">Exporter (CSV)</button><button class="btn small danger" data-act="rank-clear">Vider</button></div>
      ${R.rows.length ? `<div class="list">${R.rows.map(row).join("")}</div>` : `<div class="card empty"><p class="drop-title">Aucun élément</p><p>Ajoutez des vidéos, un dossier, des torrents ou des magnets (ou glissez-les ici) pour les classer.</p></div>`}
      ${R.estimated ? `<p class="file-meta" style="margin-top:18px">Les torrents et magnets sont estimés d'après leur nom et leur taille : leur note est moins fiable.</p>` : ""}`;
  }
  function upgrades() {
    const L = S.library;
    const card = (x) => `<div class="card up-item"><div><h3 class="up-title">${esc(x.title)}</h3>${chips(x.fix)}</div>
      <div class="gainbar"><div class="gain-num"><span>${fmt(x.now)} → ${fmt(x.target)}</span><span class="big">+${fmt(x.gain)}</span></div>
        <div class="track"><div class="ghost" style="width:${x.target}%"></div><div class="now" style="width:${x.now}%;background:${tier(x.now)}"></div></div>
        <span class="file-meta">${esc(x.size)}</span></div></div>`;
    const more = (kind, left) => (left > 0 ? `<div style="margin-top:16px;text-align:center"><button class="btn" data-act="up-more" data-kind="${kind}">Afficher plus (${left} restant${left > 1 ? "s" : ""})</button></div>` : "");
    const scan = L.scan ?`<div class="banner" style="display:block"><div class="row-between"><span>${spinner(`Analyse : ${L.scan.done} / ${L.scan.total} fichiers${L.scan.cached ? ` (${L.scan.cached} déjà en mémoire)` : ""}`)}</span><button class="btn small" data-act="up-cancel">Annuler</button></div>
      <div class="track" style="margin-top:12px"><div class="fill" style="width:${L.scan.total ? (100 * L.scan.done) / L.scan.total : 0}%;background:var(--accent)"></div></div></div>` : "";
    return `<div class="folders">${L.folders.map((f) => `<span class="folder">${esc(f)}<button aria-label="Retirer ${esc(f)}" data-act="up-remove" data-path="${esc(f)}">×</button></span>`).join("")}
        <button class="btn small" data-act="up-add">${ICON.plus}Ajouter un dossier</button></div>
      <div class="toolbar"><label class="file-meta" for="lvl">Viser</label>
        <select class="sel" id="lvl" data-act="up-level">${L.levels.map((l) => `<option ${l === L.level ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
        <button class="btn primary" data-act="up-scan" ${L.scan ? "disabled" : ""}>Analyser les dossiers</button></div>
      <div class="banner"><b>À viser</b><span>${esc(L.wanted)}</span>${L.summary ? `<span class="file-meta">· ${esc(L.summary)}</span>` : ""}</div>${scan}
      ${L.hasResults ? `<div class="section" style="margin-top:36px"><h2 class="section-title">Films à améliorer <span class="file-meta">(${L.filmsTotal})</span></h2>
        <p class="section-sub">Du plus gros gain possible au plus petit.</p><div class="list">${L.films.map(card).join("") || '<div class="card empty"><p>Rien à améliorer à ce niveau.</p></div>'}</div>${more("films", L.filmsTotal - L.films.length)}</div>
        <div class="section" style="margin-top:40px"><h2 class="section-title">Séries à améliorer <span class="file-meta">(${L.seriesTotal} saison${L.seriesTotal > 1 ? "s" : ""})</span></h2>
        <p class="section-sub">Une ligne par saison.</p><div class="list">${L.series.map(card).join("") || '<div class="card empty"><p>Rien à améliorer à ce niveau.</p></div>'}</div>${more("series", L.seriesTotal - L.series.length)}</div>
        <div style="margin-top:24px"><button class="btn small" data-act="up-export">Exporter la liste (CSV)</button></div>`
      : `<div class="card empty" style="margin-top:28px"><p class="drop-title">Aucune analyse pour l'instant</p><p>Ajoutez vos dossiers de films et de séries, puis lancez l'analyse. Le logiciel indique quoi viser, pas où le trouver.</p></div>`}`;
  }
  function libraryView() {
    const seg = `<div class="seg" role="group"><button aria-pressed="${ui.lib === "rank"}" data-act="lib" data-v="rank">Classement</button><button aria-pressed="${ui.lib === "up"}" data-act="lib" data-v="up">Pistes d'amélioration</button></div>`;
    return `<div class="page">${head("Bibliothèque", "Classez plusieurs versions, ou repérez ce qui gagnerait à exister en meilleure qualité.")}<div style="margin-bottom:28px">${seg}</div>${ui.lib === "rank" ? ranking() : upgrades()}</div>`;
  }

  /* ---------- Historique ---------- */
  function historyView() {
    const H = S.history;
    return `<div class="page">${head("Historique", "Chaque comparaison est gardée ici. Refaire la même comparaison met la ligne à jour.")}
      <div class="toolbar" style="margin-top:0"><button class="btn small" data-act="hist-export">Exporter (CSV)</button><button class="btn small danger" data-act="hist-clear">Tout effacer</button></div>
      ${H.length ? `<div class="list">${H.map((h) => `<div class="card hist"><div class="hist-date">${esc(h.date)}</div>
        ${["a", "b"].map((k, i) => { const sc = h["s" + k]; return `<div class="hist-side ${h.winner === "AB"[i] ? "win" : ""}"><div class="n" title="${esc(h[k])}">${esc(h[k])}</div><div class="s" style="color:${tier(sc)}">${fmt(sc)}</div></div>`; }).join("")}
        <div class="hist-actions"><button class="btn small" data-act="hist-open" data-id="${h.id}">Rouvrir</button><button class="btn small danger" data-act="hist-remove" data-id="${h.id}">Supprimer</button></div></div>`).join("")}</div>`
      : `<div class="card empty"><p class="drop-title">Pas encore de comparaison</p><p>Elles apparaîtront ici automatiquement.</p></div>`}</div>`;
  }

  /* ---------- Réglages ---------- */
  function settingsView() {
    const s = S.settings;
    const segOf = (items, cur, act) => `<div class="seg" role="group">${items.map(([v, l]) => `<button aria-pressed="${v === cur}" data-act="${act}" data-v="${esc(v)}">${esc(l)}</button>`).join("")}</div>`;
    const same = (arr) => arr.map((x) => [x, x]);
    return `<div class="page">${head("Réglages", "Ce qui compte pour vous dans la note, ce que votre matériel sait lire, et l'apparence.")}
      <div class="grid2">
        <section class="card panel"><h3>Apparence</h3><p class="hint">Le mode OLED utilise un noir pur : les pixels s'éteignent sur un écran OLED.</p>${segOf([["cinema", "Cinéma"], ["oled", "OLED"]], S.theme, "theme-set")}</section>
        <section class="card panel"><h3>Langue souhaitée</h3><p class="hint">Retire quelques points aux versions sans le français que vous voulez.</p>${segOf(s.langs, s.lang, "lang-set")}</section>
        <section class="card panel" style="grid-column:1/-1"><h3>Ce qui compte pour vous</h3><p class="hint">Choisissez un profil, ou réglez l'importance de chaque critère dans la note finale.</p>
          ${segOf(same(s.profiles), s.profile, "profile-set")}
          <div class="sliders">${s.weights.map(([k, l, v]) => `<div class="slider-row"><span>${esc(l)}</span><input type="range" min="0" max="40" value="${v}" data-act="weight" data-key="${k}" aria-label="${esc(l)}"><span class="num">${v}</span></div>`).join("")}</div></section>
        <section class="card panel"><h3>Votre matériel</h3><p class="hint">Ce qui n'est pas lu est pénalisé : un Dolby Vision devient du HDR10.</p>
          <div class="stack"><select class="sel" data-act="preset" aria-label="Modèle de matériel">${s.presets.map((p) => `<option ${p === s.preset ? "selected" : ""}>${esc(p)}</option>`).join("")}</select></div>
          <div class="switches" style="margin-top:20px">${s.device.map(([k, l, on]) => `<label class="switch"><span>${esc(l)}</span><span class="sw"><input type="checkbox" data-act="device" data-key="${k}" ${on ? "checked" : ""}><span></span></span></label>`).join("")}</div>
          <div class="field" style="margin-top:22px"><span>Résolution maximale de l'écran</span>${segOf(same(["2160p", "1080p"]), s.maxRes, "maxres")}</div></section>
        <section class="card panel"><h3>Torrents et magnets</h3><p class="hint">Durée supposée du film, pour estimer le débit d'après la taille.</p>
          <div class="field"><span>Durée</span><div class="stepper"><button data-act="runtime" data-d="-10" aria-label="Moins">−</button><span class="num">${s.runtime} min</span><button data-act="runtime" data-d="10" aria-label="Plus">+</button></div></div>
          ${S.ffmpeg.ok ? "" : `<div class="field" style="margin-top:22px"><span>ffprobe introuvable</span><button class="btn small" data-act="pick-ffprobe">Indiquer ffprobe.exe</button></div>`}</section>
        <section class="card panel" style="grid-column:1/-1"><div class="row-between"><div><h3>Diagnostic</h3><p class="hint" style="margin-bottom:0">VidCompare ${esc(S.version)}. Si quelque chose ne marche pas, le journal des erreurs aide à comprendre pourquoi.</p></div>
          <button class="btn small" data-act="open-log">Ouvrir le dossier du journal</button></div></section>
        <section class="card panel" style="grid-column:1/-1"><div class="row-between"><div><h3>Réputation des groupes</h3><p class="hint" style="margin-bottom:0">Un bonus ou un malus de -10 à +10 points. Vide au départ : le logiciel ne juge aucun groupe à votre place.</p></div>
          <button class="btn small" data-act="group-add">${ICON.plus}Ajouter un groupe</button></div>
          <div style="margin-top:14px">${s.groups.length ? s.groups.map(([g, v]) => `<div class="group-row"><span>${esc(g)}</span><span class="row-actions"><span class="stepper small"><button data-act="group-step" data-name="${esc(g)}" data-v="${v}" data-d="-1" aria-label="Moins">−</button><span class="num ${v >= 0 ? "pos" : "neg"}">${v > 0 ? "+" : ""}${v}</span><button data-act="group-step" data-name="${esc(g)}" data-v="${v}" data-d="1" aria-label="Plus">+</button></span><button class="btn small danger" data-act="group-remove" data-name="${esc(g)}">Retirer</button></span></div>`).join("") : `<p class="file-meta">Aucun groupe pour l'instant.</p>`}</div></section>
      </div></div>`;
  }

  /* ---------- rendu ---------- */
  const VIEWS = { compare: compareView, library: libraryView, history: historyView, settings: settingsView };
  function render() {
    if (!S) return;
    document.body.dataset.theme = S.theme === "oled" ? "oled" : "cinema";
    $("#nav").innerHTML = NAV.map(([id, label]) => `<button data-act="nav" data-v="${id}" ${ui.view === id ? 'aria-current="page"' : ""}>${ICON[id]}<span>${label}</span></button>`).join("");
    $("#theme-seg").innerHTML = [["cinema", "Cinéma"], ["oled", "OLED"]].map(([v, l]) => `<button aria-pressed="${v === S.theme}" data-act="theme-set" data-v="${v}">${l}</button>`).join("");
    $("#version").textContent = "Version " + S.version;
    $("#ffmpeg-status").innerHTML = S.ffmpeg.ok ? `<i class="dot ok"></i><span>FFmpeg prêt</span>` : `<i class="dot bad"></i><span>FFmpeg introuvable</span>`;
    const banner = S.ffmpeg.ok ? "" : `<div class="warn-banner"><span>FFmpeg (ffprobe) est introuvable : les vidéos ne pourront pas être lues. Installez-le avec « winget install Gyan.FFmpeg » ou indiquez ffprobe.exe.</span><button class="btn small" data-act="pick-ffprobe">Indiquer ffprobe.exe</button></div>`;
    const main = $("#main");
    main.innerHTML = banner + VIEWS[ui.view]();
    if (ui.animate) requestAnimationFrame(() => requestAnimationFrame(() => {
      $$(".ring .value, .mini-ring .value", main).forEach((c) => (c.style.strokeDashoffset = c.dataset.offset));
      $$(".fill[data-w]", main).forEach((f) => (f.style.width = f.dataset.w + "%"));
    }));
  }

  /* ---------- actions ---------- */
  const ask = {
    magnet: (cb) => textModal("Lien magnet", "Collez le lien magnet complet (il doit contenir un nom : paramètre dn).", "magnet:?xt=urn:btih:…&dn=…", "Ajouter", cb),
    path: (what, cb) => textModal(what, "Mode développement : indiquez le chemin complet.", "C:\\Films\\Film.mkv", "Valider", cb),
  };
  async function openFrames() {
    const r = await call("show_frames");
    if (!r || !r.ok) { toast((r && r.error) || "Images indisponibles."); return; }
    let i = 0;
    const m = modal({ title: "Images côte à côte", hint: `A : ${r.nameA}   ·   B : ${r.nameB}`, ok: "Fermer", wide: true, onOk: () => true,
      body: `${(r.warnings || []).map((w) => `<p class="file-meta ${w.level === "alert" ? "err" : ""}">${esc(w.text)}</p>`).join("")}<div class="gallery"><img alt="Image comparée, A à gauche et B à droite"><div class="gallery-nav"><button class="btn small" data-g="-1">◀ Précédente</button><span class="file-meta" id="g-cap"></span><button class="btn small" data-g="1">Suivante ▶</button></div><p class="file-meta">Les images HDR sont converties en SDR pour être comparables.</p></div>` });
    $('[data-m="cancel"]', m).remove();
    const show = () => { $("img", m).src = r.frames[i].src; const t = r.frames[i].t; $("#g-cap", m).textContent = `Image ${i + 1} sur ${r.frames.length} · à ${Math.floor(t / 60)} min ${String(t % 60).padStart(2, "0")} s`; };
    m.addEventListener("click", (e) => { const g = e.target.closest("[data-g]"); if (g) { i = (i + Number(g.dataset.g) + r.frames.length) % r.frames.length; show(); } });
    show();
  }
  document.addEventListener("click", async (e) => {
    const t = e.target.closest("[data-act]");
    if (!t || t.tagName === "SELECT" || t.tagName === "INPUT") return;
    const a = t.dataset.act, d = t.dataset, tag = d.tag;
    if (a === "nav") { ui.view = d.v; ui.animate = true; render(); ui.animate = false; $("#main").scrollTop = 0; return; }
    if (a === "lib") { ui.lib = d.v; ui.animate = true; render(); ui.animate = false; return; }
    if (a === "pick-video") return inApp() ? act("pick_video", tag) : ask.path("Chemin de la vidéo", (v) => act("set_source", tag, v));
    if (a === "pick-torrent") return inApp() ? act("pick_torrent", tag) : ask.path("Chemin du .torrent", (v) => act("set_source", tag, v));
    if (a === "magnet") return ask.magnet((v) => act("set_source", tag, v));
    if (a === "report") return textModal("Rapport MediaInfo", "Collez le rapport complet (vue Texte, en français ou en anglais). On le trouve souvent dans la fiche d'un torrent : le fichier n'est pas lu.", "General\nComplete name : …\n\nVideo\nFormat : HEVC\n…", "Analyser ce rapport", (v) => act("set_report", tag, v), true);
    if (a === "clear") return act("clear_slot", tag);
    if (a === "frames") return openFrames();
    if (a === "vmaf") {
      const bad = S.result.versions.find((x) => x.level === "alert");
      if (!bad) return act("run_vmaf");
      return modal({ title: "Montages différents probables", hint: bad.text, ok: "Mesurer quand même",
        body: `<p class="file-meta">Si les deux fichiers ne montrent pas les mêmes scènes au même instant, le score ne veut rien dire. Mesurez seulement si vous savez que c'est le même montage.</p>`,
        onOk: () => act("run_vmaf") });
    }
    if (a === "up-more") return act("up_more", d.kind);
    if (a === "open-log") return act("open_log_folder");
    if (a === "save-report") return act("save_report");
    if (a === "rank-pick") return inApp() ? act("rank_pick", d.v) : ask.path("Chemin d'un fichier ou dossier", (v) => act("rank_add", [v]));
    if (a === "rank-magnet") return ask.magnet((v) => act("rank_add_magnet", v));
    if (a === "rank-remove") return act("rank_remove", Number(d.id));
    if (a === "rank-send") { await act("rank_send", Number(d.id), tag); ui.view = "compare"; render(); return; }
    if (a === "rank-clear") return act("rank_clear");
    if (a === "rank-export") return act("rank_export");
    if (a === "up-add") return inApp() ? act("up_add_folder") : ask.path("Chemin du dossier", (v) => act("up_add_folder", v));
    if (a === "up-remove") return act("up_remove_folder", d.path);
    if (a === "up-scan") return act("up_scan");
    if (a === "up-cancel") return act("up_cancel");
    if (a === "up-export") return act("up_export");
    if (a === "hist-open") { await act("hist_reopen", Number(d.id)); ui.view = "compare"; render(); return; }
    if (a === "hist-remove") return act("hist_remove", Number(d.id));
    if (a === "hist-clear") return modal({ title: "Tout effacer ?", hint: "Tout l'historique sera supprimé.", ok: "Effacer", body: "", onOk: () => act("hist_clear") });
    if (a === "hist-export") return act("hist_export");
    if (a === "theme-set") return act("set_theme", d.v);
    if (a === "lang-set") return act("set_lang", d.v);
    if (a === "profile-set") return act("set_profile", d.v);
    if (a === "maxres") return act("set_max_res", d.v);
    if (a === "runtime") return act("set_runtime", S.settings.runtime + Number(d.d));
    if (a === "pick-ffprobe") return act("pick_ffprobe");
    if (a === "group-add") return modal({ title: "Nouveau groupe", hint: "Le nom du groupe est la fin du nom de fichier, après le dernier tiret.", ok: "Ajouter",
      body: `<input id="g-name" class="field-text" placeholder="NOMDUGROUPE"><label class="file-meta" for="g-bonus" style="display:block;margin:14px 0 6px">Bonus (-10 à +10)</label><input id="g-bonus" class="field-text" type="number" min="-10" max="10" step="1" value="0">`,
      onOk: (b) => { const n = $("#g-name", b).value.trim(); if (!n) return false; return act("group_set", n, Number($("#g-bonus", b).value || 0)); } });
    if (a === "group-step") return act("group_set", d.name, Math.max(-10, Math.min(10, Number(d.v) + Number(d.d))));
    if (a === "group-remove") return act("group_remove", d.name);
  });
  document.addEventListener("change", (e) => {
    const t = e.target, a = t.dataset && t.dataset.act;
    if (!a) return;
    if (a === "weight") act("set_weight", t.dataset.key, Number(t.value));
    else if (a === "device") act("set_device", t.dataset.key, t.checked);
    else if (a === "preset") act("set_preset", t.value);
    else if (a === "up-level") act("up_set_level", t.value);
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
    if (!sources.length) { if (files.length) toast("Impossible de lire le chemin de ce fichier : utilisez « Choisir une vidéo »."); return; }
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
    const s = await call("get_state");
    if (s && s.slots) { setState(s); return; }
    $("#main").innerHTML = `<div class="page"><h1 class="page-title">Moteur indisponible</h1><p class="page-sub">L'interface n'arrive pas à joindre le moteur de VidCompare. Relancez le logiciel.</p></div>`;
  }
  let started = false;
  const start = () => { if (!started) { started = true; boot(); } };
  window.addEventListener("pywebviewready", start);
  setTimeout(() => { if (!window.pywebview) start(); }, 500);       // mode développement : pas de pywebview
  if (window.pywebview && window.pywebview.api) start();
  // Tant qu'une analyse tourne en arrière-plan, on redemande l'état : filet si une notification est perdue,
  // et seul moyen de se tenir à jour en mode navigateur (sans fenêtre pywebview pour pousser l'état).
  const working = () => !!S && (["A", "B"].some((t) => S.slots[t] && S.slots[t].status === "loading") ||
    S.ranking.rows.some((r) => r.status === "loading") || !!S.library.scan || (S.result && S.result.visual.busy));
  setInterval(() => { if (working() && !document.querySelector(".modal-back")) call("get_state").then((s) => s && s.slots && setState(s)); }, 800);
})();
