"""Lecture des caractéristiques réelles d'un fichier avec ffprobe (FFmpeg)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .models import AudioTrack, MediaInfo


class FFprobeError(RuntimeError):
    pass


def find_ffprobe(custom: str | None = None) -> str | None:
    root = Path(__file__).resolve().parent.parent
    # Application figée (.exe) : ffprobe est livré à côté du programme.
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else root
    candidates = [custom, os.environ.get("VIDCOMPARE_FFPROBE"),
                  exe_dir / "bin" / "ffprobe.exe", root / "bin" / "ffprobe.exe",
                  root / "bin" / "ffprobe"]
    for c in candidates:
        if c and Path(c).is_file():
            return str(c)
    return shutil.which("ffprobe")


def _run(cmd: list[str]) -> dict:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=flags, timeout=180)
    if p.returncode != 0:
        raise FFprobeError(p.stderr.strip() or "ffprobe a échoué")
    return json.loads(p.stdout or "{}")


def run_ffprobe(target: str, ffprobe: str | None = None) -> dict:
    exe = find_ffprobe(ffprobe)
    if not exe:
        raise FFprobeError(
            "ffprobe est introuvable. Installez FFmpeg (winget install Gyan.FFmpeg) "
            "ou indiquez l'emplacement de ffprobe.exe.")
    data = _run([exe, "-v", "error", "-print_format", "json",
                 "-show_format", "-show_streams", target])
    # Le HDR10+ n'apparaît que dans les métadonnées de la première image.
    try:
        frames = _run([exe, "-v", "error", "-print_format", "json", "-select_streams", "v:0",
                       "-show_frames", "-read_intervals", "%+#1", target])
        data["_first_frame"] = (frames.get("frames") or [{}])[0]
    except (FFprobeError, subprocess.TimeoutExpired, json.JSONDecodeError):
        data["_first_frame"] = {}
    return data


def load_media(path: str, ffprobe: str | None = None) -> MediaInfo:
    """Analyse un fichier. Un .iso est ouvert via le protocole bluray: de FFmpeg."""
    p = Path(path)
    size = p.stat().st_size if p.exists() else 0
    if p.suffix.lower() == ".iso":
        try:
            return parse_probe(run_ffprobe("bluray:" + str(p), ffprobe), path, size)
        except (FFprobeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            if find_ffprobe(ffprobe) is None:
                raise
            info = MediaInfo(path=path, filename=p.name, size_bytes=size, container="ISO", partial=True)
            info.notes.append(f"Contenu du disque illisible par FFmpeg ({exc}). Seul le nom est analysé.")
            return info
    return parse_probe(run_ffprobe(str(p), ffprobe), path, size)


# --- interprétation ------------------------------------------------------

def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v) -> int | None:
    n = _num(v)
    return None if n is None else int(n)


def _fraction(v: str | None) -> float | None:
    if not v or "/" not in v:
        return _num(v)
    a, _, b = v.partition("/")
    a, b = _num(a), _num(b)
    return a / b if a is not None and b else None


def _tag_bitrate(stream: dict) -> int | None:
    for k, v in (stream.get("tags") or {}).items():
        if k.upper().startswith("BPS"):
            return _int(v)
    return None


def classify_hdr(stream: dict, first_frame: dict) -> tuple[str, bool]:
    side = list(stream.get("side_data_list") or [])
    frame_side = list(first_frame.get("side_data_list") or [])
    hdr10plus = any("2094-40" in s.get("side_data_type", "") or "HDR10+" in s.get("side_data_type", "")
                    for s in side + frame_side)
    dv = next((s for s in side if "DOVI" in s.get("side_data_type", "")
               or "Dolby Vision" in s.get("side_data_type", "")), None)
    transfer = stream.get("color_transfer")
    if dv:
        profile = _int(dv.get("dv_profile"))
        compat = _int(dv.get("dv_bl_signal_compatibility_id"))
        if profile == 7:
            return "DV P7", hdr10plus
        if profile == 8:
            return {4: "DV P8.4", 2: "DV P8.2"}.get(compat, "DV P8.1"), hdr10plus
        if profile == 5:
            return "DV P5", hdr10plus
        return "DV autre", hdr10plus
    if hdr10plus:
        return "HDR10+", True
    if transfer == "smpte2084":
        return "HDR10", False
    if transfer == "arib-std-b67":
        return "HLG", False
    return "SDR", False


def audio_label(stream: dict) -> tuple[str, bool]:
    codec = (stream.get("codec_name") or "").lower()
    profile = (stream.get("profile") or "").lower()
    title = ((stream.get("tags") or {}).get("title") or "").lower()
    atmos = "atmos" in profile or "atmos" in title
    if codec == "truehd":
        return ("TrueHD Atmos" if atmos else "TrueHD"), True
    if codec == "eac3":
        return ("DD+ Atmos" if atmos else "DD+"), False
    if codec == "ac3":
        return "AC3", False
    if codec == "dts":
        if "dts:x" in profile or "dts-x" in profile or "dts:x" in title:
            return "DTS:X", True
        if re.search(r"\bma\b", profile):
            return "DTS-HD MA", True
        if "hra" in profile:
            return "DTS-HD HRA", False
        return "DTS", False
    if codec.startswith("pcm"):
        return "LPCM", True
    if codec in {"flac", "alac"}:
        return "FLAC", True
    if codec == "aac":
        return "AAC", False
    if codec == "mp3":
        return "MP3", False
    if codec == "opus":
        return "Opus", False
    if codec == "vorbis":
        return "Vorbis", False
    return codec.upper() or "Inconnu", False


def parse_probe(data: dict, path: str, size: int = 0) -> MediaInfo:
    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    p = Path(path)
    info = MediaInfo(
        path=path, filename=p.name,
        size_bytes=_int(fmt.get("size")) or size,
        duration=_num(fmt.get("duration")),
        container=(fmt.get("format_name") or "").split(",")[0] or None,
    )

    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), None)
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    for s in audio_streams:
        label, lossless = audio_label(s)
        tags = s.get("tags") or {}
        info.audio.append(AudioTrack(
            index=_int(s.get("index")) or 0, codec=s.get("codec_name") or "", label=label,
            channels=_int(s.get("channels")) or 0,
            bitrate=_int(s.get("bit_rate")) or _tag_bitrate(s),
            language=tags.get("language"), title=tags.get("title"), lossless=lossless))
    info.subtitle_langs = [(s.get("tags") or {}).get("language") or "?"
                           for s in streams if s.get("codec_type") == "subtitle"]

    if video:
        info.video_codec = (video.get("codec_name") or "").lower() or None
        info.width, info.height = _int(video.get("width")), _int(video.get("height"))
        info.fps = _fraction(video.get("avg_frame_rate")) or _fraction(video.get("r_frame_rate"))
        depth = _int(video.get("bits_per_raw_sample"))
        if not depth:
            pix = video.get("pix_fmt") or ""
            depth = 12 if "12" in pix else 10 if "10" in pix else 8
        info.bit_depth = depth
        info.hdr, info.hdr10plus = classify_hdr(video, data.get("_first_frame") or {})

        vbr = _int(video.get("bit_rate")) or _tag_bitrate(video)
        if vbr is None:
            total = _int(fmt.get("bit_rate"))
            if total is None and info.duration:
                total = int(info.size_bytes * 8 / info.duration)
            if total:
                vbr = max(total - sum(t.bitrate or 0 for t in info.audio), 0) or None
                info.video_bitrate_estimated = vbr is not None
        info.video_bitrate = vbr
    return info
