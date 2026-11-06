"""Garde « mêmes versions » : repère deux fichiers qui ne sont pas deux copies du même montage.

Les images côte à côte et le VMAF comparent les deux vidéos au même instant. Si l'une est un montage
différent (version salles, director's cut, IMAX plein cadre, cadence PAL), les deux fichiers ne montrent
pas les mêmes scènes au même moment et le résultat n'a plus de sens.
"""
from __future__ import annotations

from .metrics import fmt
from .models import MediaInfo, Warn

PAL_SPEEDUP = 25 / (24000 / 1001)       # un film 23,976 images/s passé à 25 : durée réduite de 4 %


def fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    if h:
        return f"{h} h {m:02d} min"
    return f"{m} min {sec:02d} s" if m else f"{sec} s"


def compare_versions(a: MediaInfo, b: MediaInfo) -> list[Warn]:
    """Écarts entre deux fichiers qui rendent une comparaison image par image douteuse.

    Un niveau « alert » veut dire : les deux fichiers ne montrent presque certainement pas les mêmes scènes.
    """
    out: list[Warn] = []
    if a.from_name or b.from_name or a.partial or b.partial:
        return out                                      # rien de mesurable sans le fichier lui-même

    if a.duration and b.duration:
        diff = abs(a.duration - b.duration)
        rel = diff / max(a.duration, b.duration)
        if diff >= 60 and rel >= 0.01:
            out.append(Warn(
                "alert", f"Durées différentes : A {fmt_duration(a.duration)}, B {fmt_duration(b.duration)} "
                         f"(écart de {fmt_duration(diff)}). Ce sont probablement deux montages différents "
                         "(version salles, director's cut, IMAX...) : les images et le VMAF compareraient "
                         "des scènes différentes."))
        elif diff >= 3 and rel >= 0.002:
            out.append(Warn("info", f"Léger écart de durée ({fmt(diff)} s) : un petit décalage de début est possible."))

    if a.fps and b.fps and abs(a.fps - b.fps) > 0.3:
        hint = ""
        slow, fast = sorted((a.fps, b.fps))
        if abs(fast / slow - PAL_SPEEDUP) < 0.01:
            hint = " L'une est probablement la version 25 images/s, accélérée de 4 % (norme PAL)."
        out.append(Warn("warn", f"Cadence différente : A {fmt(a.fps, 3)}, B {fmt(b.fps, 3)} images/s.{hint}"))

    if a.width and a.height and b.width and b.height:
        ra, rb = a.width / a.height, b.width / b.height
        if abs(ra - rb) / max(ra, rb) > 0.04:
            out.append(Warn("warn", f"Format d'image différent : A {fmt(ra, 2)}:1, B {fmt(rb, 2)}:1. "
                                    "Une version peut être recadrée ou en IMAX plein cadre."))

    if a.chapters and b.chapters and len(a.chapters) != len(b.chapters):
        out.append(Warn("info", f"Nombre de chapitres différent : A {len(a.chapters)}, B {len(b.chapters)}."))
    return out


def needs_confirmation(issues: list[Warn]) -> bool:
    return any(i.level == "alert" for i in issues)
