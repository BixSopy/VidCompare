"""Mesures objectives : résolution, bits par pixel, note de débit."""
from __future__ import annotations

from .models import MediaInfo

# Efficacité de chaque codec par rapport au H.264 (1,0).
CODEC_GAIN = {
    "av1": 1.7, "hevc": 1.4, "vp9": 1.3, "h264": 1.0,
    "vc1": 0.9, "mpeg4": 0.8, "mpeg2video": 0.5,
}

# (bits par pixel normalisés, note)
BPP_ANCHORS = [(0.0, 5), (0.02, 25), (0.04, 40), (0.07, 55), (0.10, 68),
               (0.14, 80), (0.20, 90), (0.30, 100)]

REF_PIXELS = 1920 * 1080


def resolution_tier(width: int | None, height: int | None) -> tuple[str, str]:
    """Renvoie (clé de RESOLUTION_SCORES, palier).

    On prend la hauteur « équivalente 16:9 » pour que les films en format
    large (1920×800) restent classés en 1080p.
    """
    if not width or not height:
        return "", ""
    eff = max(height, width * 9 / 16)
    if eff >= 3400:
        return "4320p (8K)", "8k"
    if eff >= 1600:
        return "2160p (4K UHD)", "uhd"
    if eff >= 900:
        return "1080p (Full HD)", "fhd"
    if eff >= 600:
        return "720p (HD)", "hd"
    if eff >= 400:
        return "576p / 480p (DVD)", "sd"
    return "≤360p", "ld"


def bits_per_pixel(info: MediaInfo) -> float | None:
    if not (info.video_bitrate and info.width and info.height and info.fps):
        return None
    return info.video_bitrate / (info.width * info.height * info.fps)


def normalized_bpp(info: MediaInfo) -> float | None:
    """Bits par pixel ramenés à un équivalent H.264 en 1080p."""
    bpp = bits_per_pixel(info)
    if bpp is None:
        return None
    gain = CODEC_GAIN.get(info.video_codec or "", 1.0)
    scale = (info.width * info.height / REF_PIXELS) ** 0.25
    return bpp * gain * scale


def bitrate_score(nbpp: float) -> int:
    pts = BPP_ANCHORS
    if nbpp >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= nbpp <= x1:
            return round(y0 + (y1 - y0) * (nbpp - x0) / (x1 - x0))
    return pts[0][1]


def fmt(x: float, digits: int = 1) -> str:
    """Nombre avec le séparateur décimal de la langue active (virgule en français, point en anglais...)."""
    from .i18n import decimal_sep
    return f"{x:.{digits}f}".replace(".", decimal_sep())


def mbps(bits: int | None) -> float | None:
    return None if bits is None else bits / 1_000_000
