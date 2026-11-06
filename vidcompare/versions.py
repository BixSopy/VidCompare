"""Garde « mêmes versions » : repère deux fichiers qui ne sont pas deux copies du même montage.

Les images côte à côte et le VMAF comparent les deux vidéos au même instant. Si l'une est un montage
différent (version salles, director's cut, IMAX plein cadre, cadence PAL), les deux fichiers ne montrent
pas les mêmes scènes au même moment et le résultat n'a plus de sens.
"""
from __future__ import annotations

from .i18n import t
from .metrics import fmt
from .models import MediaInfo, Warn

PAL_SPEEDUP = 25 / (24000 / 1001)       # un film 23,976 images/s passé à 25 : durée réduite de 4 %


def fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    if h:
        return t("dur.h_min", h=h, m=f"{m:02d}")
    return t("dur.min_s", m=m, s=f"{sec:02d}") if m else t("dur.s", s=sec)


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
            out.append(Warn("alert", t("ver.duration", a=fmt_duration(a.duration), b=fmt_duration(b.duration),
                                       gap=fmt_duration(diff))))
        elif diff >= 3 and rel >= 0.002:
            out.append(Warn("info", t("ver.small_gap", s=fmt(diff))))

    if a.fps and b.fps and abs(a.fps - b.fps) > 0.3:
        hint = ""
        slow, fast = sorted((a.fps, b.fps))
        if abs(fast / slow - PAL_SPEEDUP) < 0.01:
            hint = t("ver.pal")
        out.append(Warn("warn", t("ver.fps", a=fmt(a.fps, 3), b=fmt(b.fps, 3), hint=hint)))

    if a.width and a.height and b.width and b.height:
        ra, rb = a.width / a.height, b.width / b.height
        if abs(ra - rb) / max(ra, rb) > 0.04:
            out.append(Warn("warn", t("ver.aspect", a=fmt(ra, 2), b=fmt(rb, 2))))

    if a.chapters and b.chapters and len(a.chapters) != len(b.chapters):
        out.append(Warn("info", t("ver.chapters", a=len(a.chapters), b=len(b.chapters))))
    return out


def needs_confirmation(issues: list[Warn]) -> bool:
    return any(i.level == "alert" for i in issues)
