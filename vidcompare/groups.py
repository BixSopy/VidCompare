"""Réputation des groupes de release : bonus ou malus réglable par l'utilisateur.

Stocké dans `%APPDATA%\\VidCompare\\groupes.json`, par exemple {"NOMDUGROUPE": 3, "AUTRE": -5}.
Un bonus va de -10 à +10 points sur la note finale. Aucune valeur par défaut : le logiciel
ne juge aucun groupe à votre place.
"""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

LIMIT = 10


def default_path() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "VidCompare" / "groupes.json"


def _legacy() -> list[Path]:
    """Anciens emplacements (fichier posé à côté du programme)."""
    root = Path(__file__).resolve().parent.parent
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else root
    return [exe_dir / "groupes.json", root / "groupes.json"]


def _clamp(v) -> float:
    return max(-LIMIT, min(LIMIT, float(v)))


def load(path: Path | None = None) -> dict[str, float]:
    """Groupes et bonus tels que saisis (casse conservée)."""
    for p in ([path] if path else [default_path(), *_legacy()]):
        if p and p.is_file():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                return {str(k).strip(): _clamp(v) for k, v in raw.items() if str(k).strip()}
            except (ValueError, OSError, AttributeError, TypeError):
                return {}
    return {}


def save(data: dict[str, float], path: Path | None = None) -> None:
    p = path or default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    clean = {str(k).strip(): _clamp(v) for k, v in data.items() if str(k).strip()}
    p.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    reload()


@lru_cache(maxsize=1)
def bonuses() -> dict[str, float]:
    return {k.lower(): v for k, v in load().items()}


def reload() -> None:
    bonuses.cache_clear()
