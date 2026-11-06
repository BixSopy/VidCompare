"""Fichiers .torrent et liens magnet : estimation de la qualité d'après le nom et la taille.

Un torrent ne contient aucune donnée vidéo. On lit le nom des fichiers et leurs tailles,
puis on en déduit ce qu'on peut, en le signalant comme estimé.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus, urlparse

from .i18n import t
from .models import AudioTrack, MediaInfo
from .parse_name import NameClaims, parse_name

VIDEO_EXT = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts", ".wmv", ".webm", ".iso"}
DEFAULT_RUNTIME_MIN = 110


class TorrentError(ValueError):
    pass


@dataclass
class TorrentInfo:
    name: str
    files: list[tuple[str, int]] = field(default_factory=list)   # (chemin, octets)
    trackers: list[str] = field(default_factory=list)
    kind: str = "torrent"                                         # torrent | magnet
    size_known: bool = True

    @property
    def total(self) -> int:
        return sum(s for _, s in self.files)

    def main_file(self) -> tuple[str, int] | None:
        videos = [f for f in self.files if Path(f[0]).suffix.lower() in VIDEO_EXT]
        pool = videos or self.files
        return max(pool, key=lambda f: f[1], default=None)


# --- bencode ----------------------------------------------------------------

def _decode(b: bytes, i: int = 0, depth: int = 0):
    if depth > 64:
        raise TorrentError(t("tor.too_deep"))
    c = b[i:i + 1]
    if c == b"i":
        j = b.index(b"e", i)
        return int(b[i + 1:j]), j + 1
    if c == b"l":
        i += 1
        out = []
        while b[i:i + 1] != b"e":
            v, i = _decode(b, i, depth + 1)
            out.append(v)
        return out, i + 1
    if c == b"d":
        i += 1
        out = {}
        while b[i:i + 1] != b"e":
            k, i = _decode(b, i, depth + 1)
            v, i = _decode(b, i, depth + 1)
            out[k] = v
        return out, i + 1
    if c.isdigit():
        j = b.index(b":", i)
        n = int(b[i:j])
        start = j + 1
        if start + n > len(b):
            raise TorrentError(t("tor.truncated"))
        return b[start:start + n], start + n
    raise TorrentError(t("tor.invalid"))


def bdecode(data: bytes):
    try:
        value, end = _decode(data)
    except (ValueError, IndexError) as exc:
        raise TorrentError(t("tor.invalid")) from exc
    return value


def _text(v) -> str:
    return v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v)


def parse_torrent_bytes(data: bytes) -> TorrentInfo:
    meta = bdecode(data)
    if not isinstance(meta, dict) or not isinstance(meta.get(b"info"), dict):
        raise TorrentError(t("tor.invalid"))
    info = meta[b"info"]
    name = _text(info.get(b"name.utf-8") or info.get(b"name") or b"torrent")
    files: list[tuple[str, int]] = []
    if isinstance(info.get(b"files"), list):
        for f in info[b"files"]:
            parts = f.get(b"path.utf-8") or f.get(b"path") or []
            files.append(("/".join(_text(p) for p in parts), int(f.get(b"length", 0))))
    else:
        files.append((name, int(info.get(b"length", 0))))
    trackers = []
    if b"announce" in meta:
        trackers.append(_text(meta[b"announce"]))
    for tier in meta.get(b"announce-list", []) or []:
        trackers += [_text(tk) for tk in tier if isinstance(tk, bytes)]
    return TorrentInfo(name=name, files=files, trackers=list(dict.fromkeys(trackers)))


def parse_torrent(path: str) -> TorrentInfo:
    return parse_torrent_bytes(Path(path).read_bytes())


def parse_magnet(uri: str) -> TorrentInfo:
    u = urlparse(uri.strip())
    if u.scheme != "magnet":
        raise TorrentError(t("tor.not_magnet"))
    q = parse_qs(u.query)
    name = unquote_plus((q.get("dn") or [""])[0]).strip()
    if not name:
        raise TorrentError(t("tor.magnet_no_name"))
    size = int((q.get("xl") or ["0"])[0] or 0)
    return TorrentInfo(name=name, files=[(name, size)], trackers=q.get("tr", []),
                       kind="magnet", size_known=size > 0)


# --- estimation ---------------------------------------------------------------

_RES = {"2160p": (3840, 2160), "1080p": (1920, 1080), "720p": (1280, 720),
        "576p": (720, 576), "480p": (720, 480)}
_CODEC = {"hevc": "hevc", "h264": "h264", "av1": "av1", "vc1": "vc1",
          "mpeg2": "mpeg2video", "xvid": "mpeg4"}
_DEFAULT_CHANNELS = {"TrueHD Atmos": 8, "DTS:X": 8, "TrueHD": 6, "DTS-HD MA": 6, "DD+ Atmos": 6,
                     "DD+": 6, "AC3": 6, "DTS": 6, "DTS-HD HRA": 6, "LPCM": 6, "FLAC": 2, "AAC": 2}
_LOSSLESS = {"TrueHD Atmos", "TrueHD", "DTS:X", "DTS-HD MA", "LPCM", "FLAC"}


def merge_claims(primary: NameClaims, secondary: NameClaims) -> NameClaims:
    out = NameClaims()
    for attr in ("source", "resolution", "codec", "channels", "group", "year"):
        setattr(out, attr, getattr(primary, attr) or getattr(secondary, attr))
    out.hdr = primary.hdr | secondary.hdr
    out.audio = primary.audio | secondary.audio
    out.langs = primary.langs | secondary.langs
    return out


def _hdr_from_claims(c: NameClaims) -> str:
    if "DV" in c.hdr:
        return "DV P7" if c.source in ("Remux", "ISO", "BluRay") else "DV P8.1"
    if "HDR10+" in c.hdr:
        return "HDR10+"
    if "HDR10" in c.hdr or "HDR" in c.hdr:
        return "HDR10"
    if "HLG" in c.hdr:
        return "HLG"
    return "SDR"


def torrent_to_media(tor: TorrentInfo, runtime_min: int = DEFAULT_RUNTIME_MIN) -> MediaInfo:
    main = tor.main_file()
    fname = posixpath.basename(main[0]) if main else tor.name
    size = main[1] if main else 0
    claims = merge_claims(parse_name(tor.name), parse_name(fname))
    info = MediaInfo(path=tor.name, filename=tor.name, size_bytes=size, from_name=True, claims=claims,
                     container="torrent" if tor.kind == "torrent" else "magnet")
    info.notes.append(t("tor.note_estimated"))
    if tor.kind == "torrent" and len([f for f in tor.files if Path(f[0]).suffix.lower() in VIDEO_EXT]) > 1:
        info.notes.append(t("tor.note_multi"))

    res = _RES.get(claims.resolution or "")
    if res:
        info.width, info.height = res
    info.fps = 24000 / 1001
    codec = _CODEC.get(claims.codec or "")
    if not codec and res:
        codec = "hevc" if res[1] >= 2160 else "h264"
        info.notes.append(t("tor.note_codec", codec="HEVC" if codec == "hevc" else "H.264"))
    info.video_codec = codec
    info.hdr = _hdr_from_claims(claims) if res else None
    info.hdr10plus = "HDR10+" in claims.hdr
    info.bit_depth = 10 if info.hdr and info.hdr != "SDR" else 8 if res else None

    for i, label in enumerate(sorted(claims.audio, key=lambda l: -len(l))):
        ch = {"7.1": 8, "6.1": 7, "5.1": 6, "2.0": 2, "1.0": 1}.get(claims.channels or "",
                                                                   _DEFAULT_CHANNELS.get(label, 6))
        info.audio.append(AudioTrack(index=i, codec=label.lower(), label=label, channels=ch, bitrate=None,
                                     language=None, title=None, lossless=label in _LOSSLESS))

    if size > 0 and tor.size_known:
        info.duration = runtime_min * 60
        total_bps = size * 8 / info.duration
        audio_bps = 3_000_000 if any(a.lossless for a in info.audio) else 600_000
        info.video_bitrate = max(int(total_bps - audio_bps), 0) or None
        info.video_bitrate_estimated = True
        info.notes.append(t("tor.note_runtime", min=runtime_min))
    else:
        info.notes.append(t("tor.note_size"))
    return info
