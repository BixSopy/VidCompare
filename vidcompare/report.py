"""Verdict et explications en français, partagés par la console et l'interface."""
from __future__ import annotations

from .metrics import fmt
from .models import Comparison, Evaluation


def verdict(cmp: Comparison) -> str:
    diff = cmp.total_a - cmp.total_b
    if not cmp.contributions:
        return "Aucun critère comparable entre ces deux fichiers."
    if cmp.winner == "égalité":
        return f"Qualité équivalente (écart de {fmt(abs(diff))} point)."
    name = "Le fichier A" if cmp.winner == "A" else "Le fichier B"
    return f"{name} est de meilleure qualité, avec {fmt(abs(diff))} points d'avance."


def explanations(cmp: Comparison) -> list[str]:
    """Une ligne par critère qui fait bouger l'écart, du plus important au moins important."""
    lines = []
    for c in sorted(cmp.contributions, key=lambda c: abs(c.points), reverse=True):
        if abs(c.points) < 0.3:
            continue
        who = "A" if c.points > 0 else "B"
        better, worse = (c.a, c.b) if c.points > 0 else (c.b, c.a)
        other = "B" if who == "A" else "A"
        label = c.label if c.label.isupper() else c.label.lower()
        lines.append(f"{who} gagne {fmt(abs(c.points))} pt sur {label} : "
                     f"{better.value} contre {worse.value} pour {other}.")
    lines = lines or ["Aucun critère ne fait vraiment la différence."]
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
    if gain <= 0.5:
        return (f"{big} pèse {fmt(extra)} Go de plus que {small} ({fmt(gbig)} Go contre {fmt(gsmall)} Go) "
                f"sans noter mieux : {small} est plus économe.")
    return (f"{big} pèse {fmt(extra)} Go de plus que {small} ({fmt(gbig)} Go contre {fmt(gsmall)} Go) "
            f"pour {fmt(gain)} points de plus, soit {fmt(gain / extra, 2)} pt par Go supplémentaire.")


def ranking_rows(ranked) -> list[dict]:
    """Lignes du classement (pour la console et l'export CSV)."""
    rows = []
    for i, (ev, total) in enumerate(ranked, 1):
        info = ev.info
        rows.append({
            "rang": i, "nom": info.filename, "note": None if total is None else round(total, 1),
            "taille_go": round(info.size_bytes / 1e9, 2) if info.size_bytes else None,
            "source": ev.cats["source"].value, "resolution": ev.cats["resolution"].value,
            "hdr": ev.cats["hdr"].value, "audio": ev.cats["audio"].value,
            "estime": "oui" if info.from_name else "non",
            "alertes": sum(1 for w in ev.warnings if w.level == "alert"),
        })
    return rows


def warnings_of(ev: Evaluation) -> list[str]:
    order = {"alert": 0, "warn": 1, "info": 2}
    prefix = {"alert": "ALERTE", "warn": "Attention", "info": "Info"}
    return [f"{prefix[w.level]} : {w.text}" for w in sorted(ev.warnings, key=lambda w: order[w.level])]


def tracks_text(ev: Evaluation) -> list[str]:
    out = []
    for t in ev.info.audio:
        br = f" · {fmt(t.bitrate / 1000, 0)} kb/s" if t.bitrate else ""
        lang = t.language or "?"
        out.append(f"Audio {lang.upper()} : {t.label}, {t.channels} canaux{br}")
    if ev.info.subtitle_langs:
        out.append("Sous-titres : " + ", ".join(sorted({l.upper() for l in ev.info.subtitle_langs})))
    return out


def text_report(cmp: Comparison) -> str:
    out = [f"A : {cmp.a.info.filename}", f"B : {cmp.b.info.filename}", "",
           f"Note A : {fmt(cmp.total_a)} / 100", f"Note B : {fmt(cmp.total_b)} / 100",
           verdict(cmp), ""]
    if cmp.partial:
        out += ["(Comparaison partielle : certains critères n'ont pas pu être évalués.)", ""]
    w = max((len(c.label) for c in cmp.contributions), default=8)
    out.append(f"{'Critère'.ljust(w)} | {'A':<34} | {'B':<34} | Effet")
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
            out += ["", f"Fichier {tag} :", *[f"  - {l}" for l in lines]]
    return "\n".join(out)
