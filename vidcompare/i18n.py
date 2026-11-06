"""Traductions : catalogues JSON par langue, langue active, séparateur décimal et sens d'écriture.

Les textes vivent dans `vidcompare/locales/<code>.json` (clé -> texte, avec des `{paramètres}`).
`t("clé", nom=valeur)` cherche dans la langue active, puis en anglais, puis en français, puis renvoie la clé :
un texte manquant ne casse jamais l'application.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# code, nom dans sa langue, sens d'écriture, séparateur décimal.
# Les dix langues les plus parlées au monde par nombre total de locuteurs (Ethnologue 2025, chiffres rapportés).
LANGUAGES: list[tuple[str, str, str, str]] = [
    ("en", "English", "ltr", "."),
    ("zh", "中文（简体）", "ltr", "."),
    ("hi", "हिन्दी", "ltr", "."),
    ("es", "Español", "ltr", ","),
    ("ar", "العربية", "rtl", "."),
    ("fr", "Français", "ltr", ","),
    ("bn", "বাংলা", "ltr", "."),
    ("pt", "Português", "ltr", ","),
    ("ru", "Русский", "ltr", ","),
    ("id", "Bahasa Indonesia", "ltr", ","),
]
CODES = [c for c, *_ in LANGUAGES]
DEFAULT = "fr"
FALLBACKS = ("en", "fr")
NEUTRAL = "und"            # termes techniques identiques dans toutes les langues (HDR10+, DTS, OLED...)
MIN_COVERAGE = 0.95        # une langue incomplète n'est pas proposée dans le réglage

_current = DEFAULT
_cache: dict[str, dict[str, str]] = {}


def locales_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "vidcompare" / "locales"


def load(code: str) -> dict[str, str]:
    if code not in _cache:
        try:
            _cache[code] = json.loads((locales_dir() / f"{code}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache[code] = {}
    return _cache[code]


def reload() -> None:
    _cache.clear()


def set_language(code: str) -> str:
    """Change la langue active. Un code inconnu laisse la langue actuelle."""
    global _current
    if code in CODES:
        _current = code
    return _current


def get_language() -> str:
    return _current


def t(key: str, **params) -> str:
    text = None
    for code in (_current, NEUTRAL, *FALLBACKS):
        text = load(code).get(key)
        if text is not None:
            break
    if text is None:
        return key
    if not params:
        return text
    try:
        return text.format_map(params)
    except (KeyError, IndexError, ValueError):
        return text


def catalog(code: str | None = None) -> dict[str, str]:
    """Catalogue complet pour l'interface : texte de la langue, complété par les langues de repli."""
    code = code or _current
    merged: dict[str, str] = {}
    for c in reversed((code, NEUTRAL, *FALLBACKS)):
        merged.update(load(c))
    return merged


def info(code: str | None = None) -> tuple[str, str, str, str]:
    code = code or _current
    return next(l for l in LANGUAGES if l[0] == code)


def is_rtl(code: str | None = None) -> bool:
    return info(code)[2] == "rtl"


def decimal_sep(code: str | None = None) -> str:
    return info(code)[3]


def coverage(code: str) -> float:
    """Part des clés du français traduites dans cette langue (0 à 1)."""
    ref = load(DEFAULT)
    if not ref:
        return 0.0
    mine, neutral = load(code), load(NEUTRAL)
    return sum(1 for k in ref if mine.get(k) or neutral.get(k)) / len(ref)


def available() -> list[tuple[str, str]]:
    """Langues proposées à l'utilisateur : celles dont le catalogue est assez complet."""
    return [(c, n) for c, n, *_ in LANGUAGES if c == DEFAULT or coverage(c) >= MIN_COVERAGE]


def detect_system_language() -> str:
    """Langue de Windows si elle fait partie des langues proposées, sinon l'anglais."""
    name = ""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
            name = buf.value
    except (AttributeError, OSError, ImportError):
        import locale
        name = (locale.getlocale()[0] or "").replace("_", "-")
    code = name.split("-")[0].lower()
    return code if code in dict(available()) else "en"
