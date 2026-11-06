"""Console : python -m vidcompare A.mkv B.torrent [C.mkv ...]

Deux éléments : comparaison détaillée. Trois ou plus : classement.
Un élément peut être une vidéo, un dossier, un fichier .torrent ou un lien magnet.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import i18n
from .device import PRESETS
from .i18n import t
from .metrics import fmt
from .probe import FFprobeError, load_media
from .report import ranking_rows, text_report
from .scoring import DEFAULT_PROFILE, LANG_MODES, LEGACY_LANG_MODES, PROFILES, compare, evaluate, rank
from .torrent import (DEFAULT_RUNTIME_MIN, VIDEO_EXT, TorrentError, parse_magnet, parse_torrent,
                      torrent_to_media)


def _expand(elements: list[str]) -> list[str]:
    out = []
    for e in elements:
        if os.path.isdir(e):
            out += [os.path.join(r, n) for r, _, ns in os.walk(e) for n in sorted(ns)
                    if Path(n).suffix.lower() in VIDEO_EXT]
        else:
            out.append(e)
    return out


def _load(element: str, ffprobe: str | None, runtime: int):
    if element.lower().startswith("magnet:"):
        return torrent_to_media(parse_magnet(element), runtime)
    if element.lower().endswith(".torrent"):
        return torrent_to_media(parse_torrent(element), runtime)
    return load_media(element, ffprobe)


def _early_language(args: list[str]) -> str:
    """Langue du rapport : --lang s'il est donné, sinon la langue de Windows."""
    for i, a in enumerate(args):
        if a == "--lang" and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return i18n.detect_system_language()


def main(argv: list[str] | None = None) -> int:
    code = _early_language(sys.argv[1:] if argv is None else argv)
    i18n.set_language(code if code in i18n.CODES else "en")
    ap = argparse.ArgumentParser(description=t("cli.description"))
    ap.add_argument("elements", nargs="+", help=t("cli.elements"))
    ap.add_argument("--lang", choices=i18n.CODES, default=i18n.get_language(), help=t("cli.lang"))
    ap.add_argument("--profil", choices=list(PROFILES), default=DEFAULT_PROFILE)
    ap.add_argument("--materiel", choices=list(PRESETS), default="Sans contrainte")
    ap.add_argument("--langue", choices=[*LANG_MODES, *LEGACY_LANG_MODES], default="none", help=t("cli.audio_pref"))
    ap.add_argument("--duree", type=int, default=DEFAULT_RUNTIME_MIN, help=t("cli.runtime"))
    ap.add_argument("--ffprobe", help=t("cli.ffprobe"))
    ap.add_argument("--sortie", help=t("cli.output"))
    args = ap.parse_args(argv)

    elements = _expand(args.elements)
    if len(elements) < 2:
        print(t("cli.need_two"), file=sys.stderr)
        return 2
    try:
        evals = [evaluate(_load(e, args.ffprobe, args.duree), device=PRESETS[args.materiel], lang=args.langue,
                          lang_code=args.lang) for e in elements]
    except (FFprobeError, TorrentError, OSError) as exc:
        print(f"{t('web.error_prefix')}{exc}", file=sys.stderr)
        return 2

    weights = PROFILES[args.profil]
    if len(evals) == 2:
        report = text_report(compare(evals[0], evals[1], weights))
    else:
        lines = [t("cli.ranking_title"), ""]
        for r in ranking_rows(rank(evals, weights)):
            rank_, name, score, _size, _src, _res, _hdr, _audio, estimated, alerts = r.values()
            est = f" [{t('cli.estimated')}]" if estimated == t("csv.yes") else ""
            alert = f"  ({t('cli.alerts', n=alerts)})" if alerts else ""
            note = "—" if score is None else fmt(score)
            lines.append(f"{rank_:>2}. {note:>5}  {name}{est}{alert}")
        report = "\n".join(lines)
    if args.sortie:
        Path(args.sortie).write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
