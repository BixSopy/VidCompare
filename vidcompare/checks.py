"""Détection d'incohérences entre le nom du fichier et son contenu réel."""
from __future__ import annotations

from .metrics import fmt, normalized_bpp, resolution_tier
from .models import MediaInfo, SourceResolution, Warn
from .parse_name import NameClaims

_CODEC_FROM_NAME = {"hevc": "hevc", "h264": "h264", "av1": "av1", "vc1": "vc1",
                    "mpeg2": "mpeg2video", "xvid": "mpeg4"}
_CODEC_LABEL = {"hevc": "HEVC", "h264": "H.264", "av1": "AV1", "vc1": "VC-1",
                "mpeg2": "MPEG-2", "xvid": "XviD"}
_RES_TIER = {"2160p": {"uhd", "8k"}, "1080p": {"fhd"}, "720p": {"hd"}, "576p": {"sd"}, "480p": {"sd"}}
_STRONG_AUDIO = ["TrueHD Atmos", "DTS:X", "TrueHD", "DTS-HD MA", "DD+ Atmos"]
_ATMOS_BASE = {"TrueHD Atmos": "TrueHD", "DD+ Atmos": "DD+"}


_FR = {"fr", "fra", "fre", "french", "français", "francais"}


def is_fr(lang: str | None) -> bool:
    return bool(lang) and lang.lower() in _FR


_is_fr = is_fr


def run_checks(info: MediaInfo, claims: NameClaims, src: SourceResolution, audio_score=None) -> list[Warn]:
    w: list[Warn] = [Warn("alert", issue) for issue in src.issues]
    w += [Warn("info", n) for n in info.notes]
    if info.partial:
        w.append(Warn("warn", "Analyse détaillée impossible : seuls le nom et la source sont notés."))
        return w
    if info.from_name:   # tout vient du nom : les comparaisons nom/contenu n'ont pas de sens
        return w

    _, tier = resolution_tier(info.width, info.height)

    # résolution annoncée
    if claims.resolution and tier and tier not in _RES_TIER.get(claims.resolution, {tier}):
        w.append(Warn("alert", f"Le nom annonce {claims.resolution}, mais la vidéo fait "
                               f"{info.width}×{info.height}."))

    # 4K très peu détaillée
    nbpp = normalized_bpp(info)
    if tier in ("uhd", "8k") and nbpp is not None and nbpp < 0.06:
        w.append(Warn("warn", "4K très compressée : image probablement upscalée ou très dégradée."))
    if src.label.startswith("BluRay") and nbpp is not None and nbpp < 0.05:
        w.append(Warn("warn", "Débit très bas pour un fichier étiqueté BluRay."))

    # codec annoncé
    if claims.codec and info.video_codec and _CODEC_FROM_NAME[claims.codec] != info.video_codec:
        w.append(Warn("warn", f"Le nom annonce {_CODEC_LABEL[claims.codec]}, mais le codec réel est "
                              f"{info.video_codec.upper()}."))

    # HDR annoncé
    real = info.hdr or "SDR"
    if "DV" in claims.hdr and not real.startswith("DV"):
        w.append(Warn("alert", "Le nom annonce Dolby Vision, mais aucune couche Dolby Vision n'est présente."))
    if "HDR10+" in claims.hdr and not info.hdr10plus:
        w.append(Warn("warn", "HDR10+ annoncé mais non détecté (la détection se fait sur la première image)."))
    if ({"HDR10", "HDR"} & claims.hdr) and real == "SDR":
        w.append(Warn("alert", "Le nom annonce du HDR, mais la vidéo est en SDR."))
    if real.startswith("DV") and "DV" not in claims.hdr:
        w.append(Warn("info", "Dolby Vision présent mais non annoncé dans le nom."))
    if real != "SDR" and info.bit_depth == 8:
        w.append(Warn("warn", "HDR en 8 bits : risque de bandes de couleur visibles."))

    # audio annoncé
    labels = {t.label for t in info.audio}
    for claimed in _STRONG_AUDIO:
        if claimed in claims.audio and claimed not in labels:
            base = _ATMOS_BASE.get(claimed)
            if base and base in labels:
                w.append(Warn("warn", f"{claimed} annoncé, mais ffprobe ne signale que {base}. "
                                      "Atmos n'est pas toujours détecté par les anciennes versions."))
            else:
                w.append(Warn("alert", f"Le nom annonce {claimed}, absent des pistes audio."))
    if claims.channels and info.audio:
        top = max(t.channels for t in info.audio)
        need = {"7.1": 8, "6.1": 7, "5.1": 6}.get(claims.channels)
        if need and top < need:
            w.append(Warn("warn", f"Le nom annonce {claims.channels}, mais la meilleure piste a {top} canaux."))
    if src.label in ("Remux", "ISO / BDMV") and info.audio and not any(t.lossless for t in info.audio):
        w.append(Warn("info", "Remux sans audio HD sans perte : la piste d'origine a peut-être été retirée."))
    if not info.audio:
        w.append(Warn("alert", "Aucune piste audio dans ce fichier."))
    else:
        fr = [t for t in info.audio if _is_fr(t.language)]
        if not fr and not any(_is_fr(l) for l in info.subtitle_langs):
            w.append(Warn("info", "Ni piste audio ni sous-titres en français."))
        elif fr and audio_score:
            best_fr = max(fr, key=audio_score)
            best_all = max(info.audio, key=audio_score)
            if audio_score(best_fr) + 15 <= audio_score(best_all):
                w.append(Warn("info", f"La piste française ({best_fr.label}) est nettement moins bonne que "
                                      f"la meilleure piste ({best_all.label})."))

    # divers
    if info.video_bitrate_estimated:
        w.append(Warn("info", "Débit vidéo estimé (le fichier ne l'indique pas) : note du débit moins précise."))
    if info.duration is not None and info.duration < 180:
        w.append(Warn("info", f"Fichier très court ({fmt(info.duration / 60)} min) : échantillon ?"))
    if not info.video_codec:
        w.append(Warn("alert", "Aucune piste vidéo trouvée."))
    return w
