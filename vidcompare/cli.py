"""Console : python -m vidcompare A.mkv B.torrent [C.mkv ...]

Deux éléments : comparaison détaillée. Trois ou plus : classement.
Un élément peut être une vidéo, un dossier, un fichier .torrent ou un lien magnet.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .probe import FFprobeError, load_media
from .report import ranking_rows, text_report
from .scoring import DEFAULT_PROFILE, LANG_MODES, PROFILES, compare, evaluate, rank
from .device import PRESETS
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare la qualité de fichiers vidéo, torrents ou magnets.")
    ap.add_argument("elements", nargs="+", help="vidéos, dossiers, .torrent ou liens magnet (2 minimum)")
    ap.add_argument("--profil", choices=list(PROFILES), default=DEFAULT_PROFILE)
    ap.add_argument("--materiel", choices=list(PRESETS), default="Sans contrainte")
    ap.add_argument("--langue", choices=list(LANG_MODES), default="none",
                    help="none : aucune préférence, fr_any : VF ou sous-titres, fr_audio : VF obligatoire")
    ap.add_argument("--duree", type=int, default=DEFAULT_RUNTIME_MIN,
                    help="durée supposée en minutes pour estimer le débit des torrents")
    ap.add_argument("--ffprobe", help="chemin de ffprobe si absent du PATH")
    ap.add_argument("--sortie", help="écrit le rapport dans ce fichier texte au lieu de l'afficher")
    args = ap.parse_args(argv)

    elements = _expand(args.elements)
    if len(elements) < 2:
        print("Erreur : il faut au moins deux éléments à comparer.", file=sys.stderr)
        return 2
    try:
        evals = [evaluate(_load(e, args.ffprobe, args.duree), device=PRESETS[args.materiel], lang=args.langue)
                 for e in elements]
    except (FFprobeError, TorrentError, OSError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2

    weights = PROFILES[args.profil]
    if len(evals) == 2:
        report = text_report(compare(evals[0], evals[1], weights))
    else:
        lines = ["Classement (note sur 100)", ""]
        for r in ranking_rows(rank(evals, weights)):
            est = " [estimé]" if r["estime"] == "oui" else ""
            alert = f"  ({r['alertes']} alerte(s))" if r["alertes"] else ""
            note = "—" if r["note"] is None else str(r["note"]).replace(".", ",")
            lines.append(f"{r['rang']:>2}. {note:>5}  {r['nom']}{est}{alert}")
        report = "\n".join(lines)
    if args.sortie:
        Path(args.sortie).write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
