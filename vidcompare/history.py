"""Historique des comparaisons, gardé dans `%APPDATA%\\VidCompare\\historique.json`."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

MAX_ENTRIES = 500


def default_path() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "VidCompare" / "historique.json"


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        try:
            self.entries: list[dict] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.entries = []

    def record(self, a: dict, b: dict, winner: str, profile: str, now: datetime | None = None) -> None:
        """Ajoute une comparaison. Si la même paire vient d'être comparée, on met à jour la ligne."""
        entry = {"date": (now or datetime.now()).strftime("%Y-%m-%d %H:%M"),
                 "a": a, "b": b, "winner": winner, "profile": profile}
        same = [i for i, e in enumerate(self.entries)
                if e["a"].get("source") == a.get("source") and e["b"].get("source") == b.get("source")]
        if same:
            self.entries.pop(same[-1])
        self.entries.append(entry)
        del self.entries[:-MAX_ENTRIES]
        self.save()

    def remove(self, indexes: list[int]) -> None:
        for i in sorted(set(indexes), reverse=True):
            if 0 <= i < len(self.entries):
                del self.entries[i]
        self.save()

    def clear(self) -> None:
        self.entries = []
        self.save()

    def newest_first(self) -> list[tuple[int, dict]]:
        return list(reversed(list(enumerate(self.entries))))

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.entries, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass   # l'historique est un confort : une erreur d'écriture ne doit rien bloquer

    def rows(self) -> list[dict]:
        from .i18n import t
        from .scoring import profile_label
        out = []
        for _, e in self.newest_first():
            out.append({t("csv.date"): e["date"], t("csv.file_a"): e["a"]["name"], t("csv.score_a"): e["a"]["score"],
                        t("csv.file_b"): e["b"]["name"], t("csv.score_b"): e["b"]["score"],
                        t("csv.best"): e["winner"] if e["winner"] in ("A", "B") else t("csv.tie"),
                        t("csv.profile"): profile_label(e.get("profile", ""))})
        return out
