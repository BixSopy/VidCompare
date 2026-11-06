"""Mémoire des analyses : un fichier déjà lu et inchangé n'est pas relu au scan suivant."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .models import AudioTrack, MediaInfo


def default_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "VidCompare" / "cache.json"


def _key(path: str) -> str | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return f"{path}|{st.st_size}|{st.st_mtime_ns}"


def info_to_dict(info: MediaInfo) -> dict:
    d = asdict(info)
    d.pop("claims", None)
    return d


def info_from_dict(d: dict) -> MediaInfo:
    d = dict(d)
    d["audio"] = [AudioTrack(**t) for t in d.get("audio", [])]
    d.pop("claims", None)
    return MediaInfo(**d)


class Cache:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self.data: dict[str, dict] = {}
        self._dirty = False
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def get(self, media_path: str) -> MediaInfo | None:
        k = _key(media_path)
        if k is None or k not in self.data:
            return None
        try:
            return info_from_dict(self.data[k])
        except (TypeError, ValueError):
            return None

    def put(self, media_path: str, info: MediaInfo) -> None:
        k = _key(media_path)
        if k is not None and not info.partial:
            self.data[k] = info_to_dict(info)
            self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data), encoding="utf-8")
            self._dirty = False
        except OSError:
            pass   # le cache est un confort : une erreur d'écriture ne doit rien bloquer
