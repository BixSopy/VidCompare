"""Détection d'incohérences entre le nom du fichier et son contenu réel."""
from __future__ import annotations

from . import langs
from .i18n import t
from .metrics import fmt, normalized_bpp, resolution_tier
from .models import MediaInfo, SourceResolution, Warn
from .parse_name import NameClaims

_CODEC_FROM_NAME = {"hevc": "hevc", "h264": "h264", "av1": "av1", "vc1": "vc1",
                    "mpeg2": "mpeg2video", "xvid": "mpeg4"}
_CODEC_LABEL = {"hevc": "HEVC", "h264": "H.264", "av1": "AV1", "vc1": "VC-1", "mpeg2": "MPEG-2", "xvid": "XviD"}
_RES_TIER = {"2160p": {"uhd", "8k"}, "1080p": {"fhd"}, "720p": {"hd"}, "576p": {"sd"}, "480p": {"sd"}}
_STRONG_AUDIO = ["TrueHD Atmos", "DTS:X", "TrueHD", "DTS-HD MA", "DD+ Atmos"]
_ATMOS_BASE = {"TrueHD Atmos": "TrueHD", "DD+ Atmos": "DD+"}


def is_fr(lang: str | None) -> bool:
    return langs.matches(lang, "fr")


def _language_checks(info: MediaInfo, audio_score, mode: str, code: str) -> list[Warn]:
    """Avertissements sur la langue souhaitée (seulement si l'utilisateur a choisi une préférence)."""
    if mode == "none" or not info.audio:
        return []
    from .i18n import LANGUAGES
    name = next((n for c, n, *_ in LANGUAGES if c == code), code)
    mine = [a for a in info.audio if langs.matches(a.language, code)]
    if not mine and not any(langs.matches(s, code) for s in info.subtitle_langs):
        return [Warn("info", t("chk.no_lang", language=name))]
    if mine and audio_score:
        best_mine, best_all = max(mine, key=audio_score), max(info.audio, key=audio_score)
        if audio_score(best_mine) + 15 <= audio_score(best_all):
            return [Warn("info", t("chk.lang_weaker", language=name, mine=best_mine.label, best=best_all.label))]
    return []


def run_checks(info: MediaInfo, claims: NameClaims, src: SourceResolution, audio_score=None,
               lang_mode: str = "none", lang_code: str = "fr") -> list[Warn]:
    w: list[Warn] = [Warn("alert", issue) for issue in src.issues]
    w += [Warn("info", n) for n in info.notes]
    if info.partial:
        w.append(Warn("warn", t("chk.partial")))
        return w
    if info.from_name:   # tout vient du nom : les comparaisons nom/contenu n'ont pas de sens
        return w

    _, tier = resolution_tier(info.width, info.height)

    # résolution annoncée
    if claims.resolution and tier and tier not in _RES_TIER.get(claims.resolution, {tier}):
        w.append(Warn("alert", t("chk.res_mismatch", claimed=claims.resolution, w=info.width, h=info.height)))

    # 4K très peu détaillée
    nbpp = normalized_bpp(info)
    if tier in ("uhd", "8k") and nbpp is not None and nbpp < 0.06:
        w.append(Warn("warn", t("chk.low_4k")))
    if src.label.startswith("BluRay") and nbpp is not None and nbpp < 0.05:
        w.append(Warn("warn", t("chk.low_bluray")))

    # codec annoncé
    if claims.codec and info.video_codec and _CODEC_FROM_NAME[claims.codec] != info.video_codec:
        w.append(Warn("warn", t("chk.codec_mismatch", claimed=_CODEC_LABEL[claims.codec], real=info.video_codec.upper())))

    # HDR annoncé
    real = info.hdr or "SDR"
    if "DV" in claims.hdr and not real.startswith("DV"):
        w.append(Warn("alert", t("chk.no_dv")))
    if "HDR10+" in claims.hdr and not info.hdr10plus:
        w.append(Warn("warn", t("chk.no_hdr10plus")))
    if ({"HDR10", "HDR"} & claims.hdr) and real == "SDR":
        w.append(Warn("alert", t("chk.no_hdr")))
    if real.startswith("DV") and "DV" not in claims.hdr:
        w.append(Warn("info", t("chk.dv_unannounced")))
    if real != "SDR" and info.bit_depth == 8:
        w.append(Warn("warn", t("chk.hdr_8bit")))

    # audio annoncé
    labels = {tr.label for tr in info.audio}
    for claimed in _STRONG_AUDIO:
        if claimed in claims.audio and claimed not in labels:
            base = _ATMOS_BASE.get(claimed)
            if base and base in labels:
                w.append(Warn("warn", t("chk.atmos_unconfirmed", claimed=claimed, base=base)))
            else:
                w.append(Warn("alert", t("chk.audio_missing", claimed=claimed)))
    if claims.channels and info.audio:
        top = max(a.channels for a in info.audio)
        need = {"7.1": 8, "6.1": 7, "5.1": 6}.get(claims.channels)
        if need and top < need:
            w.append(Warn("warn", t("chk.channels", claimed=claims.channels, top=top)))
    if src.label in ("Remux", "ISO / BDMV") and info.audio and not any(a.lossless for a in info.audio):
        w.append(Warn("info", t("chk.remux_lossy")))
    if not info.audio:
        w.append(Warn("alert", t("chk.no_audio")))
    else:
        w += _language_checks(info, audio_score, lang_mode, lang_code)

    # divers
    if info.video_bitrate_estimated:
        w.append(Warn("info", t("chk.bitrate_estimated")))
    if info.duration is not None and info.duration < 180:
        w.append(Warn("info", t("chk.short_file", minutes=fmt(info.duration / 60))))
    if not info.video_codec:
        w.append(Warn("alert", t("chk.no_video")))
    return w
