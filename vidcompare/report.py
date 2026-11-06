"""Verdict et explications dans la langue active, partagés par la console et l'interface."""
from __future__ import annotations

from .i18n import t
from .metrics import fmt
from .models import Comparison, Evaluation


def verdict(cmp: Comparison) -> str:
    diff = cmp.total_a - cmp.total_b
    if not cmp.contributions:
        return t("rep.no_criteria")
    if cmp.winner == "égalité":          # « égalité » est l'identifiant interne d'une égalité, jamais affiché
        return t("rep.tie", gap=fmt(abs(diff)))
    return t("rep.winner_a" if cmp.winner == "A" else "rep.winner_b", gap=fmt(abs(diff)))


def explanations(cmp: Comparison) -> list[str]:
    """Une ligne par critère qui fait bouger l'écart, du plus important au moins important."""
    lines = []
    for c in sorted(cmp.contributions, key=lambda c: abs(c.points), reverse=True):
        if abs(c.points) < 0.3:
            continue
        who = "A" if c.points > 0 else "B"
        better, worse = (c.a, c.b) if c.points > 0 else (c.b, c.a)
        other = "B" if who == "A" else "A"
        lines.append(t("rep.gain", who=who, pts=fmt(abs(c.points)), label=c.label, better=better.value,
                       worse=worse.value, other=other))
    lines = lines or [t("rep.nothing")]
    size = size_line(cmp)
    return lines + ([size] if size else [])


def size_line(cmp: Comparison) -> str | None:
    """Rapport qualité/taille : points gagnés pour chaque Go en plus."""
    ga, gb = cmp.a.info.size_bytes / 1e9, cmp.b.info.size_bytes / 1e9
    if not ga or not gb or abs(ga - gb) < 0.5:
        return None
    (big, small, tb, ts) = ("A", "B", cmp.total_a, cmp.total_b) if ga > gb else ("B", "A", cmp.total_b, cmp.total_a)
    gbig, gsmall = max(ga, gb), min(ga, gb)
    extra = gbig - gsmall
    gain = tb - ts
    common = dict(big=big, small=small, extra=fmt(extra), gbig=fmt(gbig), gsmall=fmt(gsmall))
    if gain <= 0.5:
        return t("rep.size_no_gain", **common)
    return t("rep.size_gain", gain=fmt(gain), per_gb=fmt(gain / extra, 2), **common)


def ranking_rows(ranked) -> list[dict]:
    """Lignes du classement (pour la console et l'export CSV), colonnes dans la langue active."""
    rows = []
    for i, (ev, total) in enumerate(ranked, 1):
        info = ev.info
        rows.append({
            t("csv.rank"): i, t("csv.name"): info.filename,
            t("csv.score"): None if total is None else round(total, 1),
            t("csv.size_gb"): round(info.size_bytes / 1e9, 2) if info.size_bytes else None,
            t("csv.source"): ev.cats["source"].value, t("csv.resolution"): ev.cats["resolution"].value,
            t("csv.hdr"): ev.cats["hdr"].value, t("csv.audio"): ev.cats["audio"].value,
            t("csv.estimated"): t("csv.yes") if info.from_name else t("csv.no"),
            t("csv.alerts"): sum(1 for w in ev.warnings if w.level == "alert"),
        })
    return rows


def warnings_of(ev: Evaluation) -> list[str]:
    order = {"alert": 0, "warn": 1, "info": 2}
    return [f"{t('sev.' + w.level)} : {w.text}" for w in sorted(ev.warnings, key=lambda w: order[w.level])]


def tracks_text(ev: Evaluation) -> list[str]:
    out = []
    for tr in ev.info.audio:
        br = f" · {fmt(tr.bitrate / 1000, 0)} kb/s" if tr.bitrate else ""
        out.append(t("rep.track", lang=(tr.language or "?").upper(), label=tr.label, ch=tr.channels, br=br))
    if ev.info.subtitle_langs:
        out.append(t("rep.subs", langs=", ".join(sorted({s.upper() for s in ev.info.subtitle_langs}))))
    return out


def text_report(cmp: Comparison) -> str:
    out = [f"A : {cmp.a.info.filename}", f"B : {cmp.b.info.filename}", "",
           t("rep.score_a", v=fmt(cmp.total_a)), t("rep.score_b", v=fmt(cmp.total_b)),
           verdict(cmp), ""]
    if cmp.partial:
        out += [t("rep.partial"), ""]
    w = max((len(c.label) for c in cmp.contributions), default=8)
    out.append(f"{t('rep.criterion').ljust(w)} | {'A':<34} | {'B':<34} | {t('rep.effect')}")
    for c in cmp.contributions:
        sign = "+" if c.points >= 0 else "-"
        side = "A" if c.points >= 0 else "B"
        sa = "" if c.a.score is None else c.a.score
        sb = "" if c.b.score is None else c.b.score
        out.append(f"{c.label.ljust(w)} | {c.a.value[:28]:<28} {sa:>3} | "
                   f"{c.b.value[:28]:<28} {sb:>3} | {side} {sign}{fmt(abs(c.points))}")
    out += ["", *explanations(cmp)]
    for tag, ev in (("A", cmp.a), ("B", cmp.b)):
        lines = warnings_of(ev) + tracks_text(ev)
        if lines:
            out += ["", t("rep.file", tag=tag), *[f"  - {x}" for x in lines]]
    return "\n".join(out)
