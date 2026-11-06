"""Lecture d'un rapport MediaInfo collé en texte (vue « Texte », en anglais ou en français).

Les fiches de torrents contiennent souvent ce rapport : on obtient les vraies pistes
(HDR, audio, débit) sans rien télécharger.
"""
from __future__ import annotations

import re
from pathlib import PureWindowsPath

from . import langs
from .i18n import t
from .models import AudioTrack, MediaInfo


class MediaInfoError(ValueError):
    pass


_ALIASES = {
    "name": ("complete name", "nom complet", "file name", "nom du fichier"),
    "size": ("file size", "taille du fichier", "taille"),
    "duration": ("duration", "durée"),
    "overall": ("overall bit rate", "débit global", "débit total"),
    "format": ("format",),
    "bitrate": ("bit rate", "débit", "nominal bit rate", "débit nominal"),
    "width": ("width", "largeur"),
    "height": ("height", "hauteur"),
    "fps": ("frame rate", "fréquence d'image", "fréquence d’image"),
    "depth": ("bit depth", "profondeur de bit", "profondeur de bits"),
    "hdr": ("hdr format", "format hdr"),
    "transfer": ("transfer characteristics", "caractéristiques de transfert"),
    "commercial": ("commercial name", "nom commercial"),
    "channels": ("channel(s)", "channels", "canaux", "canal (aux)", "canal(aux)"),
    "language": ("language", "langue"),
    "title": ("title", "titre"),
}
_KEY = {alias: key for key, aliases in _ALIASES.items() for alias in aliases}
_SECTION = re.compile(r"^(general|général|video|vidéo|audio|text|texte|menu|other|autre|image)\b", re.I)
_LINE = re.compile(r"^\s*([^:]+?)\s*:\s*(.*)$")


def _sections(text: str) -> list[tuple[str, dict[str, str]]]:
    out: list[tuple[str, dict[str, str]]] = []
    cur: dict[str, str] | None = None
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if _SECTION.match(line) and ":" not in line:
            kind = _SECTION.match(line).group(1).lower()
            kind = {"général": "general", "vidéo": "video", "texte": "text", "autre": "other"}.get(kind, kind)
            cur = {}
            out.append((kind, cur))
            continue
        m = _LINE.match(raw)
        if m and cur is not None:
            key = _KEY.get(m.group(1).strip().lower())
            if key and key not in cur:      # on garde la première valeur (la plus générale)
                cur[key] = m.group(2).strip()
    return out


def _lang(name: str | None) -> str | None:
    """Code de langue court : « French », « Français » ou « fra » donnent « fr » ; une langue inconnue garde ses deux premières lettres."""
    name = (name or "").strip()
    return langs.to_code(name) or (name[:2].lower() or None)


def _number(s: str | None) -> tuple[float, str] | None:
    if not s:
        return None
    s = re.sub(r"[\s  ]+", "", s)
    m = re.match(r"([\d.,]+)([A-Za-zµ/]*)", s)
    if not m:
        return None
    num = m.group(1)
    num = num.replace(",", ".") if "," in num and "." not in num else num.replace(",", "")
    try:
        return float(num), m.group(2).lower()
    except ValueError:
        return None


_BITRATE = {"b/s": 1, "kb/s": 1e3, "mb/s": 1e6, "gb/s": 1e9, "bps": 1, "kbps": 1e3, "mbps": 1e6}
_SIZE = {"b": 1, "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4,
         "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "kio": 1024, "mio": 1024 ** 2, "gio": 1024 ** 3,
         "ko": 1e3, "mo": 1e6, "go": 1e9, "to": 1e12}


def _bitrate(s: str | None) -> int | None:
    n = _number(s)
    return int(n[0] * _BITRATE[n[1]]) if n and n[1] in _BITRATE else None


def _size(s: str | None) -> int:
    n = _number(s)
    return int(n[0] * _SIZE[n[1]]) if n and n[1] in _SIZE else 0


def _duration(s: str | None) -> float | None:
    if not s:
        return None
    total, found = 0.0, False
    for pat, mult in ((r"(\d+)\s*h", 3600), (r"(\d+)\s*(?:min|mn)", 60), (r"(\d+)\s*s\b", 1), (r"(\d+)\s*ms", 0.001)):
        m = re.search(pat, s)
        if m:
            total += int(m.group(1)) * mult
            found = True
    return total if found else None


def _hdr(fmt: str, transfer: str) -> tuple[str, bool]:
    low = (fmt or "").lower()
    plus = "hdr10+" in low or "2094" in low
    if "dolby vision" in low:
        m = re.search(r"profile\s*(\d+)", low) or re.search(r"dv[a-z]{2}\.0?(\d)", low)
        profile = int(m.group(1)) if m else 0
        if profile == 7:
            return "DV P7", plus
        if profile == 8:
            return ("DV P8.4" if "hlg" in low else "DV P8.2" if "sdr" in low else "DV P8.1"), plus
        if profile == 5:
            return "DV P5", plus
        return "DV autre", plus
    if plus:
        return "HDR10+", True
    if "hdr10" in low or "2086" in low or "pq" in (transfer or "").lower() or "2084" in (transfer or ""):
        return "HDR10", False
    if "hlg" in low or "hlg" in (transfer or "").lower() or "b67" in (transfer or "").lower():
        return "HLG", False
    return "SDR", False


def _audio_label(fmt: str, commercial: str) -> tuple[str, bool]:
    t = f"{commercial} {fmt}".lower()
    atmos = "atmos" in t
    if "truehd" in t or "mlp" in t:
        return ("TrueHD Atmos" if atmos else "TrueHD"), True
    if "dts" in t:
        if "dts:x" in t or "dts-x" in t or "dts x" in t:
            return "DTS:X", True
        if "master audio" in t or "xll" in t or "dts-hd ma" in t:
            return "DTS-HD MA", True
        if "high resolution" in t or "hra" in t or "xbr" in t:
            return "DTS-HD HRA", False
        return "DTS", False
    if "e-ac-3" in t or "digital plus" in t or "eac3" in t:
        return ("DD+ Atmos" if atmos else "DD+"), False
    if "ac-3" in t or "dolby digital" in t or "ac3" in t:
        return "AC3", False
    if "flac" in t:
        return "FLAC", True
    if "pcm" in t:
        return "LPCM", True
    if "aac" in t:
        return "AAC", False
    if "opus" in t:
        return "Opus", False
    if "vorbis" in t:
        return "Vorbis", False
    if "mpeg audio" in t or "mp3" in t:
        return "MP3", False
    return (fmt or "Inconnu"), False


_VIDEO_CODEC = (("hevc", "hevc"), ("avc", "h264"), ("av1", "av1"), ("vp9", "vp9"), ("vc-1", "vc1"),
                ("mpeg-4 visual", "mpeg4"), ("mpeg video", "mpeg2video"))


def parse_mediainfo(text: str) -> MediaInfo:
    secs = _sections(text)
    general = next((d for k, d in secs if k == "general"), {})
    video = next((d for k, d in secs if k == "video"), None)
    if video is None:
        raise MediaInfoError(t("mi.unrecognized"))
    name = general.get("name") or t("mi.default_name")
    filename = PureWindowsPath(name).name or name
    info = MediaInfo(path=name, filename=filename, size_bytes=_size(general.get("size")),
                     duration=_duration(general.get("duration")), container=general.get("format"))
    info.notes.append(t("mi.note"))

    fmt = (video.get("format") or "").lower()
    info.video_codec = next((code for key, code in _VIDEO_CODEC if key in fmt), fmt or None)
    w, h = _number(video.get("width")), _number(video.get("height"))
    info.width, info.height = (int(w[0]) if w else None), (int(h[0]) if h else None)
    fps = _number(video.get("fps"))
    info.fps = fps[0] if fps else None
    depth = _number(video.get("depth"))
    info.bit_depth = int(depth[0]) if depth else 8
    info.hdr, info.hdr10plus = _hdr(video.get("hdr", ""), video.get("transfer", ""))

    for i, (kind, d) in enumerate(s for s in secs if s[0] == "audio"):
        label, lossless = _audio_label(d.get("format", ""), d.get("commercial", ""))
        ch = _number(d.get("channels"))
        info.audio.append(AudioTrack(index=i, codec=(d.get("format") or "").lower(), label=label,
                                     channels=int(ch[0]) if ch else 0, bitrate=_bitrate(d.get("bitrate")),
                                     language=_lang(d.get("language")), title=d.get("title"), lossless=lossless))
    info.subtitle_langs = [_lang(d.get("language")) or "?" for k, d in secs if k == "text"]

    vbr = _bitrate(video.get("bitrate"))
    if vbr is None:
        total = _bitrate(general.get("overall"))
        if total:
            vbr = max(total - sum(t.bitrate or 0 for t in info.audio), 0) or None
            info.video_bitrate_estimated = vbr is not None
    info.video_bitrate = vbr
    return info
