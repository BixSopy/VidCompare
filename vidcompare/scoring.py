"""Notes sur 100 : tables de la matrice, poids, évaluation, comparaison et classement."""
from __future__ import annotations

from . import checks, groups, langs
from .device import Device, effective_audio, effective_hdr
from .i18n import LANGUAGES, t
from .metrics import (bitrate_score, bits_per_pixel, fmt, mbps, normalized_bpp,
                      resolution_tier)
from .models import (CategoryResult, Comparison, Contribution, Evaluation,
                     MediaInfo, SourceResolution, Warn)
from .parse_name import NameClaims, parse_name

# --- tables de la matrice (voir « Matrice Qualité Vidéo ») ----------------

SOURCE_SCORES = {
    "ISO / BDMV": 100, "Remux": 98, "BluRay encode 2160p": 86, "BluRay encode 1080p": 80,
    "BluRay encode ≤720p": 68, "WEB-DL": 72, "WEBRip": 60, "HDTV": 45,
    "DVD / DVDRip": 30, "TS / TC": 10, "CAM": 3,
}
RESOLUTION_SCORES = {
    "4320p (8K)": 100, "2160p (4K UHD)": 100, "1080p (Full HD)": 72,
    "720p (HD)": 48, "576p / 480p (DVD)": 26, "≤360p": 8,
}
CODEC_SCORES = {
    "av1": 94, "hevc": 90, "vp9": 78, "h264": 70, "vc1": 52, "mpeg2video": 38, "mpeg4": 18,
}
CODEC_NAMES = {
    "av1": "AV1", "hevc": "HEVC (H.265)", "vp9": "VP9", "h264": "H.264 (AVC)",
    "vc1": "VC-1", "mpeg2video": "MPEG-2", "mpeg4": "XviD / MPEG-4",
}
HDR_SCORES = {
    "DV P7": 100, "DV P8.1": 95, "HDR10+": 86, "DV P8.4": 80, "HDR10": 78,
    "DV autre": 70, "DV P8.2": 66, "DV P5": 66, "HLG": 60, "SDR": 30,
}
AUDIO_SCORES = {
    "TrueHD Atmos": 100, "DTS:X": 98, "LPCM": 95, "TrueHD": 92, "DTS-HD MA": 91,
    "FLAC": 88, "DD+ Atmos": 80, "DTS-HD HRA": 76, "DD+": 70, "DTS": 60,
    "AC3": 55, "Opus": 50, "AAC": 40, "Vorbis": 35, "MP3": 20,
}
# Débit de référence des codecs avec perte : en dessous, la note baisse.
AUDIO_REF_BITRATE = {"AC3": 448_000, "DD+": 768_000, "DD+ Atmos": 768_000,
                     "DTS": 754_000, "AAC": 256_000, "MP3": 192_000, "Opus": 128_000}
CHANNEL_SCORES = [(8, 100), (6, 86), (3, 65), (2, 50), (1, 20)]
UNREADABLE = 20      # note d'un codec vidéo que le matériel ne sait pas lire

# --- critères et poids ------------------------------------------------------

CATEGORY_KEYS = ["source", "resolution", "bitrate", "codec", "hdr", "audio", "channels"]


class _CategoryLabels:
    """Noms des critères dans la langue active : CATEGORY_LABELS["hdr"]."""

    def __getitem__(self, key: str) -> str:
        return t(f"cat.{key}")


CATEGORY_LABELS = _CategoryLabels()
# Les noms de profil servent d'identifiants dans les réglages enregistrés : ils ne sont jamais affichés tels quels.
PROFILE_KEYS = {"Équilibré": "profile.balanced", "Home cinéma": "profile.cinema",
                "Écran SDR": "profile.sdr", "Personnalisé": "profile.custom"}
CUSTOM_PROFILE = "Personnalisé"


def profile_label(profile_id: str) -> str:
    return t(PROFILE_KEYS.get(profile_id, "profile.custom"))


PROFILES: dict[str, dict[str, int]] = {
    "Équilibré":   {"source": 20, "resolution": 12, "bitrate": 18, "codec": 8, "hdr": 17, "audio": 20, "channels": 5},
    "Home cinéma": {"source": 18, "resolution": 11, "bitrate": 14, "codec": 6, "hdr": 18, "audio": 25, "channels": 8},
    "Écran SDR":   {"source": 20, "resolution": 12, "bitrate": 28, "codec": 10, "hdr": 2, "audio": 22, "channels": 6},
}
DEFAULT_PROFILE = "Équilibré"

TIER_COLORS = [(90, "#14a085"), (75, "#4caf6a"), (55, "#c4a82b"), (35, "#d9772e"), (0, "#d04848")]


def tier_color(score: float | None) -> str:
    if score is None:
        return "#888888"
    return next(c for t, c in TIER_COLORS if score >= t)


# --- source -----------------------------------------------------------------

_REMUX_MIN_MBPS = {"8k": 60, "uhd": 28, "fhd": 14, "hd": 14, "sd": 6, "ld": 6}


def _bluray_label(tier: str) -> str:
    return {"8k": "BluRay encode 2160p", "uhd": "BluRay encode 2160p",
            "fhd": "BluRay encode 1080p"}.get(tier, "BluRay encode ≤720p")


def infer_source(info: MediaInfo) -> str:
    """Estime la source d'après le débit quand le nom n'en dit rien."""
    if info.filename.lower().endswith(".iso"):
        return "ISO / BDMV"
    _, tier = resolution_tier(info.width, info.height)
    vbr = mbps(info.video_bitrate) or 0
    if tier in ("8k", "uhd"):
        return "Remux" if vbr >= 45 else "BluRay encode 2160p" if vbr >= 15 else "WEB-DL"
    if tier == "fhd":
        return "Remux" if vbr >= 20 else "BluRay encode 1080p" if vbr >= 8 else "WEB-DL"
    if tier == "hd":
        return "BluRay encode ≤720p" if vbr >= 3 else "WEB-DL"
    if tier == "sd":
        return "DVD / DVDRip"
    return "WEBRip"


def resolve_source(info: MediaInfo, claims: NameClaims) -> SourceResolution:
    _, tier = resolution_tier(info.width, info.height)
    if not tier and claims.resolution:
        tier = {"2160p": "uhd", "1080p": "fhd", "720p": "hd"}.get(claims.resolution, "sd")
    is_iso_file = info.filename.lower().endswith(".iso")
    claim = claims.source

    if info.partial:   # seul un .iso illisible arrive ici
        return SourceResolution("ISO / BDMV", t("src.iso_ext"))

    if claim is None:
        if not tier:
            return SourceResolution("WEBRip", t("src.default"))
        return SourceResolution(infer_source(info), t("src.inferred"))

    label = {
        "ISO": "ISO / BDMV" if is_iso_file else "Remux", "Remux": "Remux",
        "BluRay": _bluray_label(tier), "WEB-DL": "WEB-DL", "WEBRip": "WEBRip",
        "HDTV": "HDTV", "DVD": "DVD / DVDRip", "TS": "TS / TC", "CAM": "CAM",
    }[claim]
    res = SourceResolution(label, t("src.name"))

    vbr = mbps(info.video_bitrate)
    if label == "Remux" and vbr is not None and tier in _REMUX_MIN_MBPS and vbr < _REMUX_MIN_MBPS[tier]:
        res.label = infer_source(info)
        res.origin = t("src.corrected")
        res.issues.append(t("src.remux_low", what=t("src.what_est" if info.from_name else "src.what_file"),
                            vbr=fmt(vbr), min=_REMUX_MIN_MBPS[tier], label=res.label))
    return res


# --- évaluation d'un fichier --------------------------------------------------

def _audio_score(track, label: str | None = None) -> int:
    label = label or track.label
    score = AUDIO_SCORES.get(label, 30)
    ref = AUDIO_REF_BITRATE.get(label)
    if ref and track.bitrate:
        score -= round(12 * max(0.0, 1 - track.bitrate / ref))
    return max(score, 0)


LANG_MODES = ("none", "any", "audio")      # aucune préférence / audio ou sous-titres / audio obligatoire
LANG_PENALTY = {"any": 5.0, "audio": 8.0}
LEGACY_LANG_MODES = {"fr_any": "any", "fr_audio": "audio"}      # anciens réglages enregistrés


def lang_name(code: str) -> str:
    """Nom d'une langue dans sa propre langue (Français, Español, 中文...)."""
    return next((n for c, n, *_ in LANGUAGES if c == code), code)


def has_language(info: MediaInfo, claims: NameClaims, code: str) -> tuple[bool, bool]:
    """(audio dans cette langue présent, sous-titres dans cette langue présents)."""
    if info.from_name:     # un nom de release n'indique la langue que pour le français (MULTi, VFF, VOSTFR...)
        return (code == "fr" and "fr_audio" in claims.langs), (code == "fr" and "fr_sub" in claims.langs)
    return (any(langs.matches(a.language, code) for a in info.audio),
            any(langs.matches(s, code) for s in info.subtitle_langs))


def best_audio(info: MediaInfo, dev: Device | None = None, only_lang: str | None = None):
    """Meilleure piste lisible sur le matériel : (note, piste, libellé effectif) ou None."""
    best = None
    for tr in info.audio:
        if only_lang and not langs.matches(tr.language, only_lang):
            continue
        eff = effective_audio(tr.label, dev)
        if eff is None:
            continue
        s = _audio_score(tr, eff)
        if best is None or s > best[0]:
            best = (s, tr, eff)
    return best


def _channels_label(n: int) -> str:
    return {1: "1.0", 2: "2.0", 6: "5.1", 8: "7.1"}.get(n, t("audio.channels", n=n))


def _channel_score(n: int) -> int:
    return next((s for lo, s in CHANNEL_SCORES if n >= lo), 0)


def evaluate(info: MediaInfo, claims: NameClaims | None = None, device: Device | None = None,
             lang: str = "none", lang_code: str = "fr") -> Evaluation:
    claims = claims or info.claims or parse_name(info.filename)
    src = resolve_source(info, claims)
    cats: dict[str, CategoryResult] = {}
    dev_notes: list[str] = []
    adjusts: list[tuple] = []

    def put(key, value, score, detail=""):
        cats[key] = CategoryResult(key, CATEGORY_LABELS[key], value, score, detail)

    bonus = groups.bonuses().get((claims.group or "").lower(), 0.0)
    if bonus:
        adjusts.append(("group", t("adjust.group"), bonus, f"{claims.group} ({bonus:+g})"))

    lang = LEGACY_LANG_MODES.get(lang, lang)
    has_audio_lang, has_sub_lang = has_language(info, claims, lang_code)
    if lang in LANG_PENALTY and not info.partial:
        missing = not has_audio_lang if lang == "audio" else not (has_audio_lang or has_sub_lang)
        if missing:
            why = t("adjust.lang_unknown") if info.from_name else t(
                "adjust.lang_no_audio" if lang == "audio" else "adjust.lang_none")
            adjusts.append(("lang", t("adjust.lang"), -LANG_PENALTY[lang], f"{why} ({-LANG_PENALTY[lang]:+g})"))
        else:
            adjusts.append(("lang", t("adjust.lang"), 0.0, t("adjust.lang_ok", language=lang_name(lang_code))))

    put("source", f"{src.label}", SOURCE_SCORES[src.label], t("src.detail", origin=src.origin))

    def finish() -> Evaluation:
        warns = checks.run_checks(info, claims, src, audio_score=_audio_score, lang_mode=lang, lang_code=lang_code)
        warns += [Warn("info", n) for n in dev_notes]
        return Evaluation(info, src, cats, warns, adjusts=adjusts)

    if info.partial:
        for k in CATEGORY_KEYS[1:]:
            put(k, "—", None)
        return finish()

    # résolution
    rlabel, tier = resolution_tier(info.width, info.height)
    if rlabel:
        rscore, rvalue = RESOLUTION_SCORES[rlabel], f"{rlabel.split(' (')[0]} · {info.width}×{info.height}"
        if device and device.max_res == "1080p" and tier in ("uhd", "8k"):
            rscore = min(rscore, RESOLUTION_SCORES["1080p (Full HD)"])
            rvalue += t("res.shown_1080")
        put("resolution", rvalue, rscore)
    else:
        put("resolution", "—", None)

    # débit vidéo
    nbpp, bpp = normalized_bpp(info), bits_per_pixel(info)
    if nbpp is not None:
        vbr = mbps(info.video_bitrate)
        score = bitrate_score(nbpp)
        if src.label in ("Remux", "ISO / BDMV"):
            score = max(score, 95)   # vidéo du disque non recompressée
        mark = t("br.estimated") if info.video_bitrate_estimated else ""
        put("bitrate", f"{fmt(vbr)} Mb/s{mark} · {fmt(bpp, 3)} bit/px", score,
            t("br.equivalent", v=fmt(nbpp, 3)))
    else:
        put("bitrate", "—", None)

    # codec
    codec = info.video_codec or ""
    if codec in CODEC_SCORES:
        depth = f" · {info.bit_depth} bits" if info.bit_depth else ""
        cscore, cvalue = CODEC_SCORES[codec], CODEC_NAMES[codec] + depth
        if device and ((codec == "hevc" and not device.hevc) or (codec == "av1" and not device.av1)):
            cscore, cvalue = UNREADABLE, cvalue + t("codec.unreadable")
            dev_notes.append(t("codec.dev_note", codec=CODEC_NAMES[codec]))
        put("codec", cvalue, cscore)
    else:
        put("codec", (codec.upper() or "—"), 40 if codec else None)

    # HDR
    if info.hdr:
        key, shown, forced = effective_hdr(info.hdr, device)
        extra = " + HDR10+" if info.hdr10plus and info.hdr.startswith("DV") and key == info.hdr else ""
        put("hdr", shown + extra, forced if forced is not None else HDR_SCORES.get(key, 50))
    else:
        put("hdr", "—", None)

    # audio et canaux : meilleure piste que le matériel sait lire
    best = None
    if lang == "audio" and has_audio_lang and not info.from_name:
        best = best_audio(info, device, only_lang=lang_code)   # on note la piste dans la langue voulue, pas l'originale
    best = best or best_audio(info, device)
    if best:
        score, track, eff = best
        tag = f" · {track.language.upper()}" if track.language else ""
        shown = eff if eff == track.label else t("audio.played_as", label=track.label, eff=eff)
        put("audio", f"{shown} {_channels_label(track.channels)}{tag}", score)
        put("channels", _channels_label(track.channels), _channel_score(track.channels))
    elif info.audio:
        put("audio", t("audio.none_readable"), 10)
        put("channels", "—", None)
        dev_notes.append(t("audio.none_readable_note"))
    elif info.from_name:
        put("audio", "—", None)
        put("channels", "—", None)
    else:
        put("audio", t("audio.none"), 0)
        put("channels", "—", None)

    return finish()


# --- notes totales, comparaison, classement --------------------------------------

def total_score(ev: Evaluation, weights: dict[str, float] | None = None) -> float | None:
    """Note pondérée sur les critères évaluables, plus le bonus du groupe."""
    weights = weights or PROFILES[DEFAULT_PROFILE]
    keys = [k for k in CATEGORY_KEYS if ev.cats[k].score is not None and weights.get(k, 0) > 0]
    wsum = sum(weights[k] for k in keys)
    if not wsum:
        return None
    base = sum(ev.cats[k].score * weights[k] for k in keys) / wsum
    return max(0.0, min(100.0, base + ev.adjust))


def rank(evals: list[Evaluation], weights: dict[str, float] | None = None) -> list[tuple[Evaluation, float | None]]:
    scored = [(e, total_score(e, weights)) for e in evals]
    return sorted(scored, key=lambda p: -1 if p[1] is None else p[1], reverse=True)


def compare(a: Evaluation, b: Evaluation, weights: dict[str, float] | None = None) -> Comparison:
    weights = weights or PROFILES[DEFAULT_PROFILE]
    common = [k for k in CATEGORY_KEYS
              if a.cats[k].score is not None and b.cats[k].score is not None and weights.get(k, 0) > 0]
    wsum = sum(weights[k] for k in common)
    partial = a.info.partial or b.info.partial or a.info.from_name or b.info.from_name or len(common) < len(
        [k for k in CATEGORY_KEYS if weights.get(k, 0) > 0])
    contribs: list[Contribution] = []
    total_a = total_b = 0.0
    for k in common:
        share = weights[k] / wsum
        sa, sb = a.cats[k].score, b.cats[k].score
        total_a += sa * share
        total_b += sb * share
        contribs.append(Contribution(k, CATEGORY_LABELS[k], a.cats[k], b.cats[k], (sa - sb) * share))
    keys: dict[str, str] = {}
    for ev in (a, b):
        for key, label, *_ in ev.adjusts:
            keys.setdefault(key, label)
    for key, label in keys.items():
        def pick(ev):
            return next((x for x in ev.adjusts if x[0] == key), None)
        pa, pb = pick(a), pick(b)
        va, vb = (pa[2] if pa else 0.0), (pb[2] if pb else 0.0)
        total_a += va
        total_b += vb
        contribs.append(Contribution(
            key, label, CategoryResult(key, label, pa[3] if pa else "—", None),
            CategoryResult(key, label, pb[3] if pb else "—", None), va - vb))
    total_a, total_b = max(0.0, min(100.0, total_a)), max(0.0, min(100.0, total_b))
    diff = total_a - total_b
    winner = "A" if diff >= 1 else "B" if diff <= -1 else "égalité"
    return Comparison(a, b, total_a, total_b, contribs, winner, partial)
