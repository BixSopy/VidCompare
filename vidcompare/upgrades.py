"""Pistes d'amélioration : quels films et séries gagneraient le plus à exister en meilleure qualité.

Le résultat est une liste de critères à viser (« 2160p · Remux · Dolby Vision · TrueHD Atmos »),
jamais des liens de téléchargement. Où trouver la version est votre choix.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .device import Device, effective_audio, effective_hdr
from .i18n import t
from .metrics import fmt
from .models import Evaluation
from .parse_name import NameClaims, parse_name
from .scoring import (AUDIO_SCORES, CATEGORY_KEYS, CATEGORY_LABELS, CHANNEL_SCORES, CODEC_SCORES,
                      HDR_SCORES, PROFILES, RESOLUTION_SCORES, SOURCE_SCORES, total_score)

MIN_GAIN = 3.0        # en dessous, le fichier est considéré comme déjà bon


@dataclass(frozen=True)
class Level:
    source: str
    resolution: str
    bitrate: int
    codec: str
    hdr: str
    audio: tuple[str, ...]      # par ordre de préférence : la première lisible est retenue
    channels: int


LEVELS: dict[str, Level] = {
    "Le meilleur possible (4K Remux)": Level(
        "Remux", "2160p (4K UHD)", 100, "hevc", "DV P7",
        ("TrueHD Atmos", "DTS:X", "TrueHD", "DTS-HD MA", "DD+ Atmos", "DD+"), 8),
    "Très bon (4K ou BluRay)": Level(
        "BluRay encode 2160p", "2160p (4K UHD)", 80, "hevc", "HDR10", ("DD+ Atmos", "DD+", "AC3"), 6),
    "Correct (1080p BluRay)": Level(
        "BluRay encode 1080p", "1080p (Full HD)", 80, "h264", "SDR", ("DD+", "AC3"), 6),
}
DEFAULT_LEVEL = "Le meilleur possible (4K Remux)"
# Les noms de niveau servent d'identifiants dans les réglages enregistrés : jamais affichés tels quels.
LEVEL_KEYS = {"Le meilleur possible (4K Remux)": "level.best", "Très bon (4K ou BluRay)": "level.good",
              "Correct (1080p BluRay)": "level.ok"}


def level_label(level_id: str) -> str:
    return t(LEVEL_KEYS.get(level_id, "level.best"))


@dataclass
class Part:
    score: int
    text: str


def target_parts(level: Level, dev: Device | None) -> dict[str, Part]:
    """Ce qu'on vise, critère par critère, en tenant compte de ce que le matériel sait lire."""
    res = level.resolution
    if dev and dev.max_res == "1080p" and res.startswith("2160"):
        res = "1080p (Full HD)"
    codec = level.codec
    if dev and codec == "hevc" and not dev.hevc:
        codec = "h264"
    hdr_key, _, forced = effective_hdr(level.hdr, dev)
    audio = next((a for a in level.audio if effective_audio(a, dev) is not None), "DD+")
    audio = effective_audio(audio, dev) or "DD+"
    ch = level.channels
    ch_label = {8: "7.1", 6: "5.1"}.get(ch, str(ch))
    return {
        "source": Part(SOURCE_SCORES[level.source], level.source),
        "resolution": Part(RESOLUTION_SCORES[res], res.split(" (")[0]),
        "bitrate": Part(level.bitrate, t("up.br_high" if level.bitrate >= 95 else "up.br_good")),
        "codec": Part(CODEC_SCORES[codec], {"hevc": "HEVC", "h264": "H.264"}.get(codec, codec)),
        "hdr": Part(forced if forced is not None else HDR_SCORES[hdr_key], hdr_key),
        "audio": Part(AUDIO_SCORES[audio], audio),
        "channels": Part(next(s for lo, s in CHANNEL_SCORES if ch >= lo), ch_label),
    }


def wanted_text(parts: dict[str, Part]) -> str:
    return " · ".join([parts["resolution"].text, parts["source"].text, parts["hdr"].text,
                       f"{parts['audio'].text} {parts['channels'].text}"])


@dataclass
class Improvement:
    label: str
    now: str
    wanted: str
    points: float


@dataclass
class Suggestion:
    kind: str                    # "Film" | "Série"
    title: str
    season: int | None
    files: int
    size_bytes: int
    current: float
    target: float
    gain: float
    improvements: list[Improvement] = field(default_factory=list)
    wanted: str = ""
    folder: str = ""

    @property
    def display(self) -> str:
        if self.kind == "Série":        # « Série » est l'identifiant interne du type, jamais affiché
            s = t("up.season", n=self.season) if self.season else t("up.series")
            return f"{self.title} · {s} ({t('up.episodes', n=self.files)})"
        return self.title


# --- type et titre -----------------------------------------------------------------

_SERIES_DIR = re.compile(r"(?i)\b(saisons?|seasons?|s[eé]ries?|tv ?shows?)\b")
_SEASON_DIR = re.compile(r"(?i)^(saisons?|seasons?|s)[ ._-]?\d{1,2}$")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def classify(path: str, claims: NameClaims) -> tuple[str, str, int | None]:
    """Renvoie (type, titre, saison) pour un fichier."""
    parts = Path(path).parts
    parents = list(parts[:-1])
    title = claims.title if claims.title and len(claims.title) >= 2 else None
    is_series = claims.season is not None or any(_SERIES_DIR.search(p) for p in parents[-3:])
    if is_series and (not title or title.lower().startswith("s0")):
        # fichier du type « S01E02.mkv » : le titre est dans le dossier
        names = [p for p in reversed(parents) if p and not _SEASON_DIR.match(p) and not _SERIES_DIR.fullmatch(p)]
        title = parse_name(names[0]).title or names[0] if names else Path(path).stem
    if not title:
        title = parse_name(Path(path).parent.name).title or Path(path).stem
    season = claims.season
    if is_series and season is None:
        m = next((_SEASON_DIR.match(p) for p in reversed(parents) if _SEASON_DIR.match(p)), None)
        if m:
            season = int(re.sub(r"\D", "", m.group(0)))
    return ("Série" if is_series else "Film"), _clean(title), season


# --- calcul ------------------------------------------------------------------------------

def _gain(ev: Evaluation, weights: dict[str, float], parts: dict[str, Part]):
    keys = [k for k in CATEGORY_KEYS if ev.cats[k].score is not None and weights.get(k, 0) > 0]
    wsum = sum(weights[k] for k in keys)
    if not wsum:
        return None
    current = total_score(ev, weights) or 0.0
    pts = {}
    for k in keys:
        pts[k] = max(0, parts[k].score - ev.cats[k].score) * weights[k] / wsum
    return current, pts


def build_suggestions(evals: list[Evaluation], weights: dict[str, float] | None = None,
                      dev: Device | None = None, level_name: str = DEFAULT_LEVEL):
    """Renvoie (films, séries, nombre de fichiers déjà bons, nombre total)."""
    weights = weights or PROFILES["Équilibré"]
    parts = target_parts(LEVELS[level_name], dev)
    wanted = wanted_text(parts)
    groups: dict[tuple, list] = {}
    for ev in evals:
        g = _gain(ev, weights, parts)
        if g is None:
            continue
        kind, title, season = classify(ev.info.path, ev.info.claims or parse_name(ev.info.filename))
        key = (kind, re.sub(r"[^a-z0-9]", "", title.lower()), season if kind == "Série" else ev.info.path)
        groups.setdefault(key, []).append((ev, g, title, season, kind))

    films: list[Suggestion] = []
    series: list[Suggestion] = []
    ok = 0
    for members in groups.values():
        n = len(members)
        cur = sum(m[1][0] for m in members) / n
        pts_by_cat = {k: sum(m[1][1].get(k, 0) for m in members) / n for k in CATEGORY_KEYS}
        gain = sum(pts_by_cat.values())
        if gain < MIN_GAIN:
            ok += n
            continue
        imps = []
        for k, p in sorted(pts_by_cat.items(), key=lambda kv: -kv[1]):
            if p >= 0.5:
                now = Counter(m[0].cats[k].value for m in members if m[0].cats[k].score is not None)
                short = now.most_common(1)[0][0].split(" · ")[0]    # « 4,1 Mb/s », « AAC 2.0 »...
                imps.append(Improvement(CATEGORY_LABELS[k], short, parts[k].text, p))
        first = members[0]
        sug = Suggestion(kind=first[4], title=first[2], season=first[3], files=n,
                         size_bytes=sum(m[0].info.size_bytes for m in members), current=cur,
                         target=cur + gain, gain=gain, improvements=imps[:3], wanted=wanted,
                         folder=str(Path(first[0].info.path).parent))
        (series if sug.kind == "Série" else films).append(sug)
    for lst in (films, series):
        lst.sort(key=lambda s: (-s.gain, s.current, s.title.lower()))
    return films, series, ok, len(evals)


def improvement_text(s: Suggestion) -> str:
    return " · ".join(f"{i.label} : {i.now} → {i.wanted} (+{fmt(i.points)})" for i in s.improvements)


def suggestion_rows(films: list[Suggestion], series: list[Suggestion]) -> list[dict]:
    rows = []
    for lst in (films, series):
        for rank_, s in enumerate(lst, 1):
            rows.append({
                t("csv.type"): t("csv.series" if s.kind == "Série" else "csv.film"), t("csv.priority"): rank_,
                t("csv.title"): s.title, t("csv.season"): s.season or "", t("csv.files"): s.files,
                t("csv.current"): round(s.current, 1), t("csv.target"): round(s.target, 1),
                t("csv.gain"): round(s.gain, 1), t("csv.improve"): improvement_text(s),
                t("csv.aim"): s.wanted, t("csv.size_gb"): round(s.size_bytes / 1e9, 2), t("csv.folder"): s.folder,
            })
    return rows
