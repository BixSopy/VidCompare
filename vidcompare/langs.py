"""Langues des pistes audio et des sous-titres : reconnaît un code ou un nom de langue (fra, French, Français...)."""
from __future__ import annotations

ALIASES: dict[str, tuple[str, ...]] = {
    "fr": ("fr", "fra", "fre", "french", "français", "francais"),
    "en": ("en", "eng", "english"),
    "zh": ("zh", "zho", "chi", "cmn", "yue", "chinese", "mandarin", "中文"),
    "hi": ("hi", "hin", "hindi", "हिन्दी"),
    "es": ("es", "spa", "spanish", "español", "espanol", "castellano"),
    "ar": ("ar", "ara", "arabic", "العربية"),
    "bn": ("bn", "ben", "bengali", "bangla", "বাংলা"),
    "pt": ("pt", "por", "portuguese", "português", "portugues"),
    "ru": ("ru", "rus", "russian", "русский"),
    "id": ("id", "ind", "indonesian", "bahasa indonesia"),
}
_INDEX = {alias: code for code, names in ALIASES.items() for alias in names}


def to_code(tag: str | None) -> str | None:
    """Code à deux lettres d'une langue connue, sinon None."""
    return _INDEX.get((tag or "").strip().lower())


def matches(tag: str | None, code: str) -> bool:
    return to_code(tag) == code
