"""Lecture des indications contenues dans le nom d'une release.

Le nom n'est jamais cru sur parole : il sert à connaître la source (Remux,
WEB-DL...) qu'on ne peut pas lire dans le fichier, et à vérifier la cohérence
avec ce que ffprobe mesure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePath


@dataclass
class NameClaims:
    source: str | None = None        # ISO, Remux, BluRay, WEB-DL, WEBRip, HDTV, DVD, TS, CAM
    resolution: str | None = None    # 2160p, 1080p, 720p, 576p, 480p
    codec: str | None = None         # hevc, h264, av1, vc1, mpeg2, xvid
    hdr: set[str] = field(default_factory=set)     # DV, HDR10+, HDR10, HDR, HLG
    audio: set[str] = field(default_factory=set)   # clés de AUDIO_SCORES
    channels: str | None = None      # 7.1, 5.1, 2.0...
    group: str | None = None
    year: int | None = None
    title: str | None = None         # texte avant l'année, la saison ou la qualité
    season: int | None = None        # présent pour une série (S01E02, 1x02, Saison 1)
    episode: int | None = None
    langs: set[str] = field(default_factory=set)   # fr_audio (MULTi, VFF, TRUEFRENCH...), fr_sub (VOSTFR)


_TITLE_STOP = re.compile(
    r"(?<![a-z0-9])(?:(?:19|20)\d\d|s\d{1,2}(?:[ -]?e\d{1,3})?|\d{1,2}x\d{2}|saison ?\d+|season ?\d+|"
    r"(?:2160|1080|720|576|480)[pi]|4k|uhd|remux|blu-?ray|bd-?rip|web-?dl|web-?rip|webdl|hdtv|dvd-?rip|"
    r"multi|vff|vfq|vf|vostfr|truefrench|french)(?![a-z0-9])")


def _title_and_season(stem: str) -> tuple[str | None, int | None, int | None]:
    norm = stem.replace("_", " ").replace(".", " ")
    low = norm.lower()
    season = episode = None
    m = re.search(r"(?<![a-z0-9])s(\d{1,2})[ -]?e(\d{1,3})(?![a-z0-9])", low) or \
        re.search(r"(?<![a-z0-9])(\d{1,2})x(\d{2})(?![a-z0-9])", low)
    if m:
        season, episode = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(?<![a-z0-9])(?:s|saison ?|season ?)(\d{1,2})(?![a-z0-9])", low)
        if m:
            season = int(m.group(1))
    title = None
    for stop in _TITLE_STOP.finditer(low):
        if stop.start() > 0:
            title = norm[:stop.start()].strip(" -()[]")
            break
    else:
        title = norm.strip(" -()[]")
    return (title or None), season, episode


def _has(text: str, pattern: str) -> bool:
    return re.search(rf"(?<![a-z0-9])(?:{pattern})(?![a-z0-9])", text) is not None


_NOT_GROUPS = {"dl", "hd", "ma", "hra", "rip", "x", "dtshd", "tv", "br", "bd"}


def parse_name(filename: str) -> NameClaims:
    p = PurePath(filename)
    stem = p.stem if p.suffix.lower() in {
        ".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".iso", ".mov", ".wmv", ".webm"} else p.name
    raw = stem.lower().replace("_", " ")
    text = raw.replace(".", " ")
    c = NameClaims()

    # --- source -----------------------------------------------------------
    if p.suffix.lower() == ".iso" or _has(
            text, r"bdmv|bd ?(?:25|50|66|100)|complete (?:uhd )?blu-?ray|full (?:blu-?ray|disc)"):
        c.source = "ISO"
    elif _has(text, r"remux|bd-?remux"):
        c.source = "Remux"
    elif _has(text, r"web-?rip"):
        c.source = "WEBRip"
    elif _has(text, r"web-?dl|webdl|web"):
        c.source = "WEB-DL"
    elif _has(text, r"blu-?ray|bd-?rip|br-?rip|uhd bd"):
        c.source = "BluRay"
    elif _has(text, r"hdtv|pdtv|sdtv|tv-?rip|dvb"):
        c.source = "HDTV"
    elif _has(text, r"dvd-?rip|dvd-?r|dvd ?[59]|dvdscr|dvd"):
        c.source = "DVD"
    elif _has(text, r"hd-?cam|cam(?:rip)?"):
        c.source = "CAM"
    elif _has(text, r"hd-?ts|tele-?sync|hd-?tc|tele-?cine|ts|tc"):
        c.source = "TS"

    # --- résolution -------------------------------------------------------
    m = re.search(r"(?<![a-z0-9])(2160|1080|720|576|480)[pi](?![a-z0-9])", text)
    if m:
        c.resolution = m.group(1) + "p"
    elif _has(text, r"4k|uhd"):
        c.resolution = "2160p"

    # --- codec ------------------------------------------------------------
    if _has(text, r"x ?265|h ?265|hevc"):
        c.codec = "hevc"
    elif _has(text, r"x ?264|h ?264|avc"):
        c.codec = "h264"
    elif _has(text, r"av1"):
        c.codec = "av1"
    elif _has(text, r"vc-?1"):
        c.codec = "vc1"
    elif _has(text, r"mpeg-?2"):
        c.codec = "mpeg2"
    elif _has(text, r"xvid|divx"):
        c.codec = "xvid"

    # --- HDR --------------------------------------------------------------
    if _has(text, r"dv|dovi|dolby ?vision"):
        c.hdr.add("DV")
    if re.search(r"hdr10 ?(?:\+|plus)", text):
        c.hdr.add("HDR10+")
    if re.search(r"(?<![a-z0-9])hdr10(?![a-z0-9+])", text):
        c.hdr.add("HDR10")
    if re.search(r"(?<![a-z0-9])hdr(?!10)(?![a-z0-9])", text):
        c.hdr.add("HDR")
    if _has(text, r"hlg"):
        c.hdr.add("HLG")

    # --- audio ------------------------------------------------------------
    atmos = _has(text, r"atmos")
    if _has(text, r"truehd|true-?hd"):
        c.audio.add("TrueHD Atmos" if atmos else "TrueHD")
    elif atmos:
        c.audio.add("DD+ Atmos")
    if re.search(r"dts-?x", text):
        c.audio.add("DTS:X")
    if re.search(r"dts-?hd[ -]?ma|dts-?ma", text):
        c.audio.add("DTS-HD MA")
    if re.search(r"dts-?hd[ -]?hra|dts-?hr", text):
        c.audio.add("DTS-HD HRA")
    # Les canaux sont souvent collés au codec (DDP5.1, AAC2.0) : seule une lettre bloque.
    def has_audio(pattern: str) -> bool:
        return re.search(rf"(?<![a-z0-9])(?:{pattern})(?![a-z])", text) is not None

    if has_audio(r"ddp|dd\+|e-?ac-?3|dd plus"):
        c.audio.add("DD+")
    if has_audio(r"flac"):
        c.audio.add("FLAC")
    if has_audio(r"l?pcm"):
        c.audio.add("LPCM")
    if has_audio(r"aac"):
        c.audio.add("AAC")
    if has_audio(r"ac-?3|dolby digital|dd(?= ?[257] ?[01])"):
        c.audio.add("AC3")

    m = re.search(r"(?<!\d)(7\.1|6\.1|5\.1|2\.0|1\.0)(?!\d)", raw)
    if m:
        c.channels = m.group(1)

    # --- groupe et année --------------------------------------------------
    m = re.search(r"-([a-z0-9]{2,15})(?:\[[^\]]*\])?$", stem, re.IGNORECASE)
    if m and m.group(1).lower() not in _NOT_GROUPS:
        c.group = m.group(1)
    m = re.search(r"(?<!\d)(19\d\d|20\d\d)(?!\d)", text)
    if m:
        c.year = int(m.group(1))
    c.title, c.season, c.episode = _title_and_season(stem)
    if _has(text, r"multi|vff|vfq|vfi|vf2|vf|truefrench|french"):
        c.langs.add("fr_audio")
    if _has(text, r"vostfr|subfrench|sub ?fr"):
        c.langs.add("fr_sub")
    return c
