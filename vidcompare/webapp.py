"""Application de bureau : fenêtre `pywebview` qui affiche l'interface web du dossier `ui/`.

Le moteur (analyse, notes, comparaison...) est le même que celui de la console. Cette classe
`Api` est ce que l'interface appelle ; chaque méthode renvoie l'état complet à afficher.
Mode développement : `python -m vidcompare.webapp --dev` sert l'interface et l'API en HTTP local,
ce qui permet de la tester dans un navigateur.
"""
from __future__ import annotations

import atexit
import base64
import csv
import functools
import io
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import webbrowser
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__, i18n, updates
from . import groups as groups_store
from . import vmaf
from .cache import Cache
from .device import PRESETS, Device, preset_label
from .i18n import t
from .history import History
from .mediainfo import MediaInfoError, parse_mediainfo
from .metrics import fmt
from .models import Evaluation, MediaInfo
from .probe import find_ffprobe, load_media
from .report import explanations, ranking_rows, size_line, text_report, tracks_text
from .scoring import (CATEGORY_KEYS, CATEGORY_LABELS, CUSTOM_PROFILE, DEFAULT_PROFILE, LANG_MODES,
                      LEGACY_LANG_MODES, PROFILES, compare, evaluate, profile_label, rank)
from .torrent import (DEFAULT_RUNTIME_MIN, VIDEO_EXT, TorrentError, TorrentInfo, parse_magnet,
                      parse_torrent, torrent_to_media)
from .upgrades import (DEFAULT_LEVEL, LEVELS, build_suggestions, level_label, suggestion_rows,
                       target_parts, wanted_text)
from .versions import compare_versions as vmaf_guard
from .versions import needs_confirmation

MAX_FOLDER_FILES = 300
MAX_SCAN_FILES = 3000
UP_PAGE = 50          # lignes ajoutées à chaque « Afficher plus » dans les pistes d'amélioration

log = logging.getLogger("vidcompare")


def log_path() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "VidCompare" / "vidcompare.log"


def setup_logging() -> None:
    """Journal des erreurs : `%APPDATA%\\VidCompare\\vidcompare.log` (3 fichiers de 1 Mo au plus)."""
    if log.handlers:
        return
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        return                      # pas de journal possible : l'application continue sans
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
DEVICE_KEYS = ("dv", "hdr10plus", "hdr", "dts", "truehd", "atmos", "hevc", "av1")


def kind_name(kind: str) -> str:
    return t(f"kind.{kind}")


def video_types() -> tuple[str, str]:
    return (t("web.video_files") + " (*.mkv;*.mp4;*.m4v;*.avi;*.mov;*.ts;*.m2ts;*.wmv;*.webm;*.iso)",
            t("web.all_files") + " (*.*)")


def ui_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "ui"


def settings_path() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "VidCompare" / "reglages.json"


class Store:
    """Réglages de l'utilisateur, gardés dans un petit fichier JSON."""

    def __init__(self, path: Path | None = None):
        self.path = path or settings_path()
        try:
            self.data: dict = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass      # un réglage non sauvegardé ne doit jamais bloquer l'application


@dataclass
class Item:
    id: int
    kind: str                       # file | torrent | magnet | report
    label: str
    path: str | None = None
    torrent: TorrentInfo | None = None
    info: MediaInfo | None = None
    error: str | None = None
    ranked: bool = False
    source: str = ""                # chemin, magnet ou « mediainfo:nom » : sert à rouvrir depuis l'historique


class Api:
    """Tout ce que l'interface peut demander. Les attributs commencent par « _ » pour rester privés."""

    def __init__(self, store: Store | None = None, history: History | None = None, cache: Cache | None = None):
        self._lock = threading.RLock()
        self._store = store or Store()
        self._history = history or History()
        self._cache = cache or Cache()
        self._window = None
        self._items: dict[int, Item] = {}
        self._slot: dict[str, int | None] = {"A": None, "B": None}
        self._next = 1
        # Deux files séparées : l'analyse d'une case A ou B ne doit jamais attendre derrière un scan de 3000 fichiers.
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="vc-interactif")
        self._scan_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="vc-scan")
        self._up_limit = {"films": UP_PAGE, "series": UP_PAGE}   # lignes affichées dans chaque liste
        self._rev = 0                         # change à chaque réglage : invalide les pistes d'amélioration
        self._up_infos: list[MediaInfo] = []
        self._up_ver = 0
        self._up_cache: tuple | None = None
        self._scan: dict | None = None
        self._visual = {"busy": False, "text": "", "error": False, "key": None}
        self._last_recorded: tuple | None = None
        self._last_push = 0.0
        setup_logging()
        self._sweep_old_temp()
        self._frames_dir = tempfile.mkdtemp(prefix="vidcompare_")
        atexit.register(shutil.rmtree, self._frames_dir, True)
        self._frames_cache: dict[tuple, dict] = {}
        self._toast: str | None = None
        log.info("VidCompare %s démarré", __version__)
        self._update: dict | None = None      # {'version', 'url'} si une version plus récente existe
        self._update_msg: str | None = None
        if self._store.get("update_check", True):
            self._pool.submit(self._auto_update_check)

    @staticmethod
    def _sweep_old_temp() -> None:
        """Supprime les dossiers temporaires laissés par d'anciennes sessions (plus d'une heure)."""
        limit = time.time() - 3600
        for d in Path(tempfile.gettempdir()).glob("vidcompare_*"):
            try:
                if d.is_dir() and d.stat().st_mtime < limit:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass

    # ------------------------------------------------------------------ réglages
    def _weights(self) -> dict[str, float]:
        w = self._store.get("weights")
        profile = self._store.get("profile", DEFAULT_PROFILE)
        return {k: float(v) for k, v in (w if profile == "Personnalisé" and w else PROFILES.get(profile, PROFILES[DEFAULT_PROFILE])).items()}

    def _device(self) -> Device:
        try:
            return Device(**self._store.get("device", {}))
        except TypeError:
            return Device()

    def _lang(self) -> str:
        """Préférence de langue des pistes : none, any (audio ou sous-titres) ou audio."""
        lang = LEGACY_LANG_MODES.get(self._store.get("lang", "none"), self._store.get("lang", "none"))
        return lang if lang in LANG_MODES else "none"

    def _ui_lang(self) -> str:
        """Langue de l'interface : celle choisie, sinon celle de Windows (si elle est proposée), sinon l'anglais."""
        code = self._store.get("ui_lang")
        if code not in dict(i18n.available()):
            code = i18n.detect_system_language()
        return code

    def _content_lang(self) -> str:
        """Langue souhaitée pour l'audio et les sous-titres : celle choisie, sinon celle de l'interface."""
        code = self._store.get("content_lang")
        return code if code in i18n.CODES else self._ui_lang()

    def _runtime(self) -> int:
        return int(self._store.get("runtime", DEFAULT_RUNTIME_MIN))

    def _ffprobe(self) -> str | None:
        return find_ffprobe(self._store.get("ffprobe"))

    def _level(self) -> str:
        lv = self._store.get("up_level", DEFAULT_LEVEL)
        return lv if lv in LEVELS else DEFAULT_LEVEL

    # ------------------------------------------------------------------ évaluation
    def _info_of(self, item: Item) -> MediaInfo | None:
        return torrent_to_media(item.torrent, self._runtime()) if item.torrent else item.info

    def _evals(self) -> dict[int, Evaluation]:
        dev, lang, code = self._device(), self._lang(), self._content_lang()
        out = {}
        for item in self._items.values():
            info = self._info_of(item)
            if info is not None:
                out[item.id] = evaluate(info, device=dev, lang=lang, lang_code=code)
        return out

    # ------------------------------------------------------------------ état pour l'interface
    def get_state(self) -> dict:
        with self._lock:
            return self._state()

    def _state(self) -> dict:
        i18n.set_language(self._ui_lang())          # les textes produits ci-dessous sont dans la langue choisie
        evals = self._evals()
        weights = self._weights()
        ia, ib = self._slot["A"], self._slot["B"]
        state = {
            "ffmpeg": {"ok": bool(self._ffprobe()), "hasFfmpeg": bool(vmaf.find_ffmpeg(self._store.get("ffprobe")))},
            "theme": self._store.get("theme", "cinema"), "version": __version__,
            "update": self._update, "updateCheck": bool(self._store.get("update_check", True)),
            "lang": i18n.get_language(), "rtl": i18n.is_rtl(),
            "toast": self._toast,
            "slots": {tag: self._slot_state(tag, evals) for tag in "AB"},
            "result": None,
            "ranking": self._ranking_state(evals, weights),
            "library": self._library_state(weights),
            "history": [],
            "settings": self._settings_state(),
        }
        if ia in evals and ib in evals:
            cmp = compare(evals[ia], evals[ib], weights)
            state["result"] = self._result_state(cmp, ia, ib)
            self._record_history(cmp, ia, ib)
        state["history"] = self._history_state()      # après l'enregistrement : la ligne du jour est incluse
        self._toast = None
        return state

    def _slot_state(self, tag: str, evals: dict) -> dict | None:
        i = self._slot[tag]
        if i is None:
            return None
        item = self._items[i]
        d = {"name": item.label, "kind": kind_name(item.kind), "status": "loading", "size": "", "chips": [], "note": ""}
        if item.error:
            d.update(status="error", note=item.error)
        elif i in evals:
            ev = evals[i]
            d["status"] = "ready"
            d["size"] = t("unit.gb", v=fmt(ev.info.size_bytes / 1e9)) if ev.info.size_bytes else ""
            d["chips"] = [ev.cats[k].value.split(" · ")[0] for k in ("resolution", "hdr", "audio")
                          if ev.cats[k].score is not None and ev.cats[k].value]
            if ev.info.from_name:
                d["note"] = t("web.estimated_note")
        return d

    def _result_state(self, cmp, ia: int, ib: int) -> dict:
        reasons = []
        for c in sorted(cmp.contributions, key=lambda c: abs(c.points), reverse=True)[:3]:
            if abs(c.points) < 0.3:
                continue
            better, worse = (c.a, c.b) if c.points > 0 else (c.b, c.a)
            reasons.append({"label": c.label, "points": round(abs(c.points), 1), "who": "A" if c.points > 0 else "B",
                            "text": t("web.vs", better=better.value, worse=worse.value)})
        warn_order = {"alert": 0, "warn": 1, "info": 2}
        alerts = {tag: [{"level": w.level, "text": w.text}
                        for w in sorted(ev.warnings, key=lambda w: warn_order[w.level])]
                  for tag, ev in (("A", cmp.a), ("B", cmp.b))}
        ready = self._visual_ready()
        key = (ia, ib)
        if self._visual["key"] != key:
            self._visual.update(key=key, text="", error=False)
        issues = vmaf_guard(cmp.a.info, cmp.b.info)
        return {
            "versions": [{"level": w.level, "text": w.text} for w in issues],
            "versionsBlock": needs_confirmation(issues),
            "total": {"A": round(cmp.total_a, 1), "B": round(cmp.total_b, 1)},
            "winner": cmp.winner, "gap": round(abs(cmp.total_a - cmp.total_b), 1), "partial": cmp.partial,
            "reasons": reasons, "sizeNote": size_line(cmp) or "",
            "rows": [{"key": c.label, "a": [c.a.value, c.a.score], "b": [c.b.value, c.b.score],
                      "adv": round(c.points, 1)} for c in cmp.contributions],
            "alerts": alerts, "tracks": {"A": tracks_text(cmp.a), "B": tracks_text(cmp.b)},
            "why": explanations(cmp),
            "visual": {"available": bool(ready), "busy": self._visual["busy"], "text": self._visual["text"],
                       "error": self._visual["error"],
                       "hint": t("web.visual_hint" if ready else "web.visual_unavailable")},
        }

    def _ranking_state(self, evals: dict, weights: dict) -> dict:
        mine = [i for i, it in self._items.items() if it.ranked]
        ranked = rank([evals[i] for i in mine if i in evals], weights)
        by_eval = {id(evals[i]): i for i in evals}
        rows = []
        for n, (ev, total) in enumerate(ranked, 1):
            item = self._items[by_eval[id(ev)]]
            rows.append({"id": item.id, "rank": n, "name": item.label, "kind": kind_name(item.kind),
                         "size": t("unit.gb", v=fmt(ev.info.size_bytes / 1e9)) if ev.info.size_bytes else "?",
                         "score": None if total is None else round(total, 1), "status": "ready",
                         "chips": [ev.cats[k].value.split(" · ")[0] for k in ("source", "resolution", "hdr", "audio")
                                   if ev.cats[k].score is not None],
                         "alerts": sum(1 for w in ev.warnings if w.level == "alert")})
        for i in mine:
            if i not in evals:
                it = self._items[i]
                rows.append({"id": i, "rank": None, "name": it.label, "kind": kind_name(it.kind), "size": "",
                             "score": None, "chips": [], "alerts": 0,
                             "status": "error" if it.error else "loading", "note": it.error or ""})
        return {"rows": rows, "estimated": any(evals[i].info.from_name for i in mine if i in evals)}

    def _library_state(self, weights: dict) -> dict:
        dev, level = self._device(), self._level()
        parts = target_parts(LEVELS[level], dev)
        lib = {"folders": list(self._store.get("up_folders", [])), "level": level,
               "levels": [[k, level_label(k)] for k in LEVELS],
               "wanted": wanted_text(parts), "scan": None, "summary": "", "films": [], "series": []}
        if self._scan:
            lib["scan"] = {k: self._scan[k] for k in ("done", "total", "cached", "failed")}
        if self._up_infos and not self._scan:
            key = (self._up_ver, self._rev, level, i18n.get_language())
            if not self._up_cache or self._up_cache[0] != key:
                lang, code = self._lang(), self._content_lang()
                evs = [evaluate(i, device=dev, lang=lang, lang_code=code) for i in self._up_infos]
                films, series, ok, total = build_suggestions(evs, weights, dev, level)
                self._up_cache = (key, films, series, ok, total)
            _, films, series, ok, total = self._up_cache
            conv = lambda s: {"title": s.display, "now": round(s.current, 1), "target": round(s.target, 1),
                              "gain": round(s.gain, 1),
                              "fix": [f"{i.label} : {i.now} → {i.wanted}" for i in s.improvements],
                              "size": t("unit.gb", v=fmt(s.size_bytes / 1e9)), "folder": s.folder}
            # Seules les premières lignes partent vers l'écran : 3000 fichiers pesaient 719 Ko à chaque envoi.
            lib["films"] = [conv(s) for s in films[: self._up_limit["films"]]]
            lib["series"] = [conv(s) for s in series[: self._up_limit["series"]]]
            lib["filmsTotal"], lib["seriesTotal"] = len(films), len(series)
            lib["summary"] = t("up.summary", total=total, films=len(films), seasons=len(series), ok=ok)
            lib["hasResults"] = True
        return lib

    def _history_state(self) -> list[dict]:
        out = []
        for idx, e in self._history.newest_first():
            d = e["date"]
            out.append({"id": idx, "date": d, "a": e["a"]["name"], "b": e["b"]["name"], "sa": e["a"]["score"],
                        "sb": e["b"]["score"], "winner": e["winner"], "profile": profile_label(e.get("profile", ""))})
        return out

    def _settings_state(self) -> dict:
        dev = self._device()
        w = self._weights()
        return {
            "profile": self._store.get("profile", DEFAULT_PROFILE),
            "profiles": [[p, profile_label(p)] for p in (*PROFILES, CUSTOM_PROFILE)],
            "weights": [[k, CATEGORY_LABELS[k], int(w.get(k, 0))] for k in CATEGORY_KEYS],
            "device": [[k, t(f"device.{k}"), bool(getattr(dev, k))] for k in DEVICE_KEYS],
            "preset": self._store.get("preset", "Sans contrainte"),
            "presets": [[p, preset_label(p)] for p in (*PRESETS, "Personnalisé")],
            "maxRes": dev.max_res, "lang": self._lang(),
            "langs": [[k, t(f"langmode.{k}", language=i18n.info(self._content_lang())[1])] for k in LANG_MODES],
            "uiLang": self._ui_lang(), "uiLangs": [[c, n] for c, n in i18n.available()],
            "contentLang": self._content_lang(), "contentLangs": [[c, n] for c, n, *_ in i18n.LANGUAGES],
            "runtime": self._runtime(),
            "groups": [[n, v] for n, v in sorted(groups_store.load().items(), key=lambda kv: kv[0].lower())],
        }

    # ------------------------------------------------------------------ pousser l'état vers l'interface
    def _attach(self, window) -> None:
        self._window = window

    def _push(self, throttle: float = 0.0) -> None:
        if self._window is None:
            return
        now = time.time()
        if throttle and now - self._last_push < throttle:
            return
        self._last_push = now
        try:
            self._window.evaluate_js(f"window.VC && window.VC.setState({json.dumps(self.get_state())})")
        except Exception:  # noqa: BLE001 - fenêtre fermée pendant une tâche de fond
            pass

    def _done(self, toast: str | None = None) -> dict:
        if toast is not None:          # un message posé plus tôt (ex. fichier invalide) est conservé
            self._toast = toast
        return self.get_state()

    # ------------------------------------------------------------------ éléments
    def _make_item(self, source: str, ranked: bool = False) -> Item | None:
        source = source.strip()
        try:
            if source.lower().startswith("magnet:"):
                t = parse_magnet(source)
                item = Item(self._next, "magnet", t.name, torrent=t, ranked=ranked, source=source)
            elif source.lower().endswith(".torrent"):
                t = parse_torrent(source)
                item = Item(self._next, "torrent", t.name, path=source, torrent=t, ranked=ranked, source=source)
            else:
                item = Item(self._next, "file", Path(source).name, path=source, ranked=ranked, source=source)
        except (TorrentError, OSError) as exc:
            self._toast = f"{Path(source).name or source} : {exc}"
            return None
        self._next += 1
        self._items[item.id] = item
        if item.kind == "file":
            self._pool.submit(self._probe, item.id, source)
        return item

    def _probe(self, item_id: int, path: str) -> None:
        try:
            info = load_media(path, self._store.get("ffprobe"))
            err = None
        except Exception as exc:  # noqa: BLE001 - toute erreur doit s'afficher
            info, err = None, str(exc)
            log.warning("Analyse impossible de %s : %s", path, exc)
        with self._lock:
            item = self._items.get(item_id)
            if item:
                item.info, item.error = info, err
        self._push()

    def _release(self, tag: str) -> None:
        old = self._slot[tag]
        self._slot[tag] = None
        if old is not None and old in self._items and not self._items[old].ranked and old not in self._slot.values():
            del self._items[old]

    # ------------------------------------------------------------------ cases A et B
    def set_source(self, tag: str, source: str) -> dict:
        with self._lock:
            if os.path.isdir(source):
                return self._done(t("web.is_folder"))
            item = self._make_item(source)
            if item:
                self._release(tag)
                self._slot[tag] = item.id
            return self._done()

    def pick_video(self, tag: str) -> dict:
        paths = self._dialog("open", file_types=video_types())
        return self.set_source(tag, paths[0]) if paths else self.get_state()

    def pick_torrent(self, tag: str) -> dict:
        paths = self._dialog("open", file_types=(t("web.torrents") + " (*.torrent)",))
        return self.set_source(tag, paths[0]) if paths else self.get_state()

    def set_report(self, tag: str, text: str) -> dict:
        try:
            info = parse_mediainfo(text)
        except MediaInfoError as exc:
            with self._lock:
                return self._done(str(exc))
        with self._lock:
            item = Item(self._next, "report", info.filename, info=info, source=f"mediainfo:{info.filename}")
            self._next += 1
            self._items[item.id] = item
            self._release(tag)
            self._slot[tag] = item.id
            return self._done()

    def clear_slot(self, tag: str) -> dict:
        with self._lock:
            self._release(tag)
            return self._done()

    # ------------------------------------------------------------------ classement
    def _expand(self, sources: list[str]) -> list[str]:
        files: list[str] = []
        for p in sources:
            if os.path.isdir(p):
                for root, _, names in os.walk(p):
                    for n in sorted(names):
                        f = os.path.join(root, n)
                        if Path(n).suffix.lower() in VIDEO_EXT and not (
                                "sample" in n.lower() and os.path.getsize(f) < 100_000_000):
                            files.append(f)
            else:
                files.append(p)
        return files

    def rank_add(self, sources: list[str]) -> dict:
        with self._lock:
            files = self._expand(sources)
            capped = len(files) > MAX_FOLDER_FILES
            for f in files[:MAX_FOLDER_FILES]:
                self._make_item(f, ranked=True)
            return self._done(t("web.folder_cap", n=MAX_FOLDER_FILES) if capped else None)

    def rank_pick(self, what: str) -> dict:
        kinds = {"videos": ("open", video_types()), "torrents": ("open", (t("web.torrents") + " (*.torrent)",)),
                 "folder": ("folder", ())}
        mode, types = kinds[what]
        paths = self._dialog(mode, file_types=types, multiple=True)
        return self.rank_add(paths) if paths else self.get_state()

    def rank_add_magnet(self, text: str) -> dict:
        return self.rank_add([text])

    def rank_remove(self, item_id: int) -> dict:
        with self._lock:
            it = self._items.get(item_id)
            if it:
                if item_id in self._slot.values():
                    it.ranked = False
                else:
                    del self._items[item_id]
            return self._done()

    def rank_clear(self) -> dict:
        with self._lock:
            for i in [i for i, it in self._items.items() if it.ranked]:
                if i in self._slot.values():
                    self._items[i].ranked = False
                else:
                    del self._items[i]
            return self._done()

    def rank_send(self, item_id: int, tag: str) -> dict:
        with self._lock:
            if item_id in self._items:
                self._release(tag)
                self._slot[tag] = item_id
            return self._done()

    def rank_export(self) -> dict:
        with self._lock:
            evals = self._evals()
            ranked = rank([evals[i] for i, it in self._items.items() if it.ranked and i in evals], self._weights())
        if not ranked:
            return self._done(t("web.rank_empty"))
        return self._write_csv("classement.csv", ranking_rows(ranked))

    # ------------------------------------------------------------------ pistes d'amélioration
    def up_add_folder(self, path: str | None = None) -> dict:
        if not path:
            picked = self._dialog("folder")
            path = picked[0] if picked else None
        with self._lock:
            if path and os.path.isdir(path):
                folders = list(self._store.get("up_folders", []))
                if path not in folders:
                    folders.append(path)
                    self._store.set("up_folders", folders)
            return self._done()

    def up_remove_folder(self, path: str) -> dict:
        with self._lock:
            self._store.set("up_folders", [f for f in self._store.get("up_folders", []) if f != path])
            return self._done()

    def up_set_level(self, name: str) -> dict:
        with self._lock:
            if name in LEVELS:
                self._store.set("up_level", name)
                self._rev += 1
                self._up_limit = {"films": UP_PAGE, "series": UP_PAGE}
            return self._done()

    def up_more(self, kind: str) -> dict:
        """Affiche une page de plus dans la liste des films ou des séries."""
        with self._lock:
            if kind in self._up_limit:
                self._up_limit[kind] += UP_PAGE
            return self._done()

    def up_scan(self) -> dict:
        with self._lock:
            folders = self._store.get("up_folders", [])
            if not folders:
                return self._done(t("web.add_folder_first"))
            files = list(dict.fromkeys(self._expand(folders)))
            capped = len(files) > MAX_SCAN_FILES
            files = files[:MAX_SCAN_FILES]
            if not files:
                return self._done(t("web.no_video"))
            token = object()
            self._up_limit = {"films": UP_PAGE, "series": UP_PAGE}
            self._up_infos = []
            self._scan = {"token": token, "done": 0, "total": len(files), "cached": 0, "failed": 0, "capped": capped}
            todo = []
            for f in files:
                info = self._cache.get(f)
                if info is not None:
                    self._up_infos.append(info)
                    self._scan["done"] += 1
                    self._scan["cached"] += 1
                else:
                    todo.append(f)
            for f in todo:
                self._scan_pool.submit(self._scan_one, token, f)
            if not todo:
                self._scan_finish(token)
            return self._done()

    def _scan_one(self, token, path: str) -> None:
        with self._lock:
            if not self._scan or self._scan["token"] is not token:
                return
        try:
            info, ok = load_media(path, self._store.get("ffprobe")), True
        except Exception as exc:  # noqa: BLE001
            info, ok = None, False
            log.warning("Scan : %s illisible : %s", path, exc)
        with self._lock:
            if not self._scan or self._scan["token"] is not token:
                return
            if ok:
                self._up_infos.append(info)
                self._cache.put(path, info)
            else:
                self._scan["failed"] += 1
            self._scan["done"] += 1
            finished = self._scan["done"] >= self._scan["total"]
        if finished:
            self._scan_finish(token)
        else:
            self._push(throttle=0.25)

    def _scan_finish(self, token) -> None:
        with self._lock:
            if not self._scan or self._scan["token"] is not token:
                return
            self._cache.save()
            self._up_ver += 1
            failed, capped = self._scan["failed"], self._scan["capped"]
            self._scan = None
            extra = []
            if failed:
                extra.append(t("web.scan_failed", n=failed))
            if capped:
                extra.append(t("web.scan_capped", n=MAX_SCAN_FILES))
            self._toast = ", ".join(extra) or None
        self._push()

    def up_cancel(self) -> dict:
        with self._lock:
            self._scan = None
            return self._done(t("web.scan_cancelled"))

    def up_export(self) -> dict:
        with self._lock:
            self.get_state()
            if not self._up_cache:
                return self._done(t("web.nothing_to_export"))
            _, films, series, _, _ = self._up_cache
            rows = suggestion_rows(films, series)
        return self._write_csv("pistes-amelioration.csv", rows) if rows else self._done(t("web.nothing_to_improve"))

    # ------------------------------------------------------------------ historique
    def _record_history(self, cmp, ia: int, ib: int) -> None:
        a, b = self._items[ia], self._items[ib]
        if not a.source or not b.source:
            return
        profile = self._store.get("profile", DEFAULT_PROFILE)
        key = (a.source, b.source, round(cmp.total_a, 1), round(cmp.total_b, 1), profile)
        if key == self._last_recorded:
            return
        self._last_recorded = key
        self._history.record({"name": a.label, "source": a.source, "score": round(cmp.total_a, 1)},
                             {"name": b.label, "source": b.source, "score": round(cmp.total_b, 1)},
                             cmp.winner, profile)

    def hist_reopen(self, idx: int) -> dict:
        with self._lock:
            if not 0 <= idx < len(self._history.entries):
                return self._done()
            e = self._history.entries[idx]
            gone = [s["name"] for s in (e["a"], e["b"])
                    if s["source"].startswith("mediainfo:") or
                    (not s["source"].lower().startswith("magnet:") and not os.path.exists(s["source"]))]
            if gone:
                return self._done(t("web.reopen_failed", names=", ".join(gone)))
            for tag, side in (("A", e["a"]), ("B", e["b"])):
                item = self._make_item(side["source"])
                if item:
                    self._release(tag)
                    self._slot[tag] = item.id
            return self._done()

    def hist_remove(self, idx: int) -> dict:
        with self._lock:
            self._history.remove([idx])
            return self._done()

    def hist_clear(self) -> dict:
        with self._lock:
            self._history.clear()
            self._last_recorded = None
            return self._done()

    def hist_export(self) -> dict:
        rows = self._history.rows()
        return self._write_csv("historique.csv", rows) if rows else self._done(t("web.history_empty"))

    # ------------------------------------------------------------------ réglages
    def set_profile(self, name: str) -> dict:
        with self._lock:
            if name in PROFILES:
                self._store.set("profile", name)
                self._store.set("weights", dict(PROFILES[name]))
            elif name == "Personnalisé":
                self._store.set("profile", "Personnalisé")
                self._store.set("weights", self._weights())
            self._rev += 1
            return self._done()

    def set_weight(self, key: str, value: int) -> dict:
        with self._lock:
            if key in CATEGORY_KEYS:
                w = self._weights()
                w[key] = max(0, min(40, int(value)))
                self._store.set("weights", w)
                self._store.set("profile", "Personnalisé")
                self._rev += 1
            return self._done()

    def _save_device(self, dev: Device, preset: str) -> None:
        self._store.set("device", dev.to_dict())
        self._store.set("preset", preset)
        self._rev += 1

    def set_preset(self, name: str) -> dict:
        with self._lock:
            if name in PRESETS:
                self._save_device(PRESETS[name], name)
            return self._done()

    def set_device(self, key: str, on: bool) -> dict:
        with self._lock:
            d = self._device().to_dict()
            if key in DEVICE_KEYS:
                d[key] = bool(on)
                self._save_device(Device(**d), "Personnalisé")
            return self._done()

    def set_max_res(self, value: str) -> dict:
        with self._lock:
            d = self._device().to_dict()
            d["max_res"] = "1080p" if value == "1080p" else "2160p"
            self._save_device(Device(**d), "Personnalisé")
            return self._done()

    def set_lang(self, key: str) -> dict:
        with self._lock:
            key = LEGACY_LANG_MODES.get(key, key)
            if key in LANG_MODES:
                self._store.set("lang", key)
                self._rev += 1
            return self._done()

    def set_ui_lang(self, code: str) -> dict:
        """Change la langue de l'interface (et, si rien n'a été choisi à part, celle des pistes souhaitées)."""
        with self._lock:
            if code in dict(i18n.available()):
                self._store.set("ui_lang", code)
                self._rev += 1
                self._last_recorded = None
            return self._done()

    def set_content_lang(self, code: str) -> dict:
        with self._lock:
            if code in i18n.CODES:
                self._store.set("content_lang", code)
                self._rev += 1
            return self._done()

    def get_strings(self) -> dict:
        """Textes de l'interface dans la langue active (avec repli sur l'anglais puis le français)."""
        with self._lock:
            i18n.set_language(self._ui_lang())
            return {"lang": i18n.get_language(), "rtl": i18n.is_rtl(), "strings": i18n.catalog()}

    def set_runtime(self, minutes: int) -> dict:
        with self._lock:
            self._store.set("runtime", max(20, min(400, int(minutes))))
            self._rev += 1
            return self._done()

    def group_set(self, name: str, bonus: float) -> dict:
        with self._lock:
            data = groups_store.load()
            if name.strip():
                data[name.strip()] = float(bonus)
                groups_store.save(data)
                self._rev += 1
            return self._done()

    def group_remove(self, name: str) -> dict:
        with self._lock:
            data = groups_store.load()
            data.pop(name, None)
            groups_store.save(data)
            self._rev += 1
            return self._done()

    def set_theme(self, theme: str) -> dict:
        with self._lock:
            self._store.set("theme", "oled" if theme == "oled" else "cinema")
            return self._done()

    # ------------------------------------------------------------------ comparaison visuelle
    def _visual_ready(self):
        ia, ib = self._slot["A"], self._slot["B"]
        ffmpeg = vmaf.find_ffmpeg(self._store.get("ffprobe"))
        if not ffmpeg or ia is None or ib is None:
            return None
        a, b = self._items[ia], self._items[ib]
        if a.kind != "file" or b.kind != "file" or not a.info or not b.info or a.info.partial or b.info.partial:
            return None
        if not (a.path and b.path and os.path.isfile(a.path) and os.path.isfile(b.path)):
            return None
        return a.info, b.info, ffmpeg

    def show_frames(self) -> dict:
        """Une image par extrait, A à gauche et B à droite, renvoyées en images intégrées."""
        with self._lock:
            ready = self._visual_ready()
        if not ready:
            return {"ok": False, "error": t("web.visual_unavailable_short")}
        a, b, ffmpeg = ready
        times = vmaf.sample_times(a.duration, b.duration)

        def one(i: int, t: float) -> dict:
            key = (a.path, a.size_bytes, b.path, b.size_bytes, round(t, 2))
            if key not in self._frames_cache:       # une image déjà extraite n'est pas refaite
                png = vmaf.side_by_side(ffmpeg, a, b, t, Path(self._frames_dir) / f"image{len(self._frames_cache)}_{i}.png")
                self._frames_cache[key] = {"t": round(t), "src": "data:image/png;base64," +
                                           base64.b64encode(png.read_bytes()).decode()}
            return self._frames_cache[key]
        try:
            with ThreadPoolExecutor(max_workers=len(times)) as pool:       # les extraits en parallèle
                frames = list(pool.map(lambda it: one(*it), enumerate(times)))
        except Exception as exc:  # noqa: BLE001
            log.warning("Images côte à côte : %s", exc)
            return {"ok": False, "error": str(exc)}
        warnings = [{"level": w.level, "text": w.text} for w in vmaf_guard(a, b)]
        return {"ok": True, "frames": frames, "nameA": a.filename, "nameB": b.filename, "warnings": warnings}

    def run_vmaf(self) -> dict:
        with self._lock:
            ready = self._visual_ready()
            if not ready or self._visual["busy"]:
                return self._done()
            a, b, ffmpeg = ready
            ia, ib = self._slot["A"], self._slot["B"]
            evals = self._evals()
            cmp = compare(evals[ia], evals[ib], self._weights())
            ref_tag = "B" if cmp.winner == "B" else "A"
            ref, dist = (a, b) if ref_tag == "A" else (b, a)
            dist_tag = "B" if ref_tag == "A" else "A"
            self._visual.update(busy=True, text=t("web.measuring"), error=False)
        threading.Thread(target=self._vmaf_worker, args=(ffmpeg, ref, dist, ref_tag, dist_tag), daemon=True).start()
        return self.get_state()

    def _vmaf_worker(self, ffmpeg, ref, dist, ref_tag, dist_tag) -> None:
        def progress(done, total):
            self._visual["text"] = t("web.measuring_n", done=done, total=total)
            self._push(throttle=0.5)
        try:
            times = vmaf.sample_times(ref.duration, dist.duration)
            score = vmaf.measure_vmaf(ffmpeg, ref, dist, times, progress=progress)
            hdr = t("web.vmaf_hdr") if any(i.hdr and i.hdr != "SDR" for i in (ref, dist)) else ""
            text = t("web.vmaf_result", dist=dist_tag, ref=ref_tag, score=fmt(score), desc=vmaf.describe(score),
                     n=len(times), sec=vmaf.SAMPLE_SECONDS, hdr=hdr)
            err = False
        except Exception as exc:  # noqa: BLE001
            text, err = t("web.error_prefix") + str(exc), True
            log.warning("VMAF : %s", exc)
        with self._lock:
            self._visual.update(busy=False, text=text, error=err)
        self._push()

    # ------------------------------------------------------------------ exports et fenêtres
    def _dialog(self, mode: str, file_types=(), multiple: bool = False, save_name: str = "") -> list[str]:
        if self._window is None:
            return []
        import webview
        kind = {"open": webview.FileDialog.OPEN, "folder": webview.FileDialog.FOLDER,
                "save": webview.FileDialog.SAVE}[mode]
        res = self._window.create_file_dialog(kind, allow_multiple=multiple, file_types=file_types,
                                              save_filename=save_name)
        if not res:
            return []
        return [res] if isinstance(res, str) else list(res)

    def _write_csv(self, default_name: str, rows: list[dict]) -> dict:
        paths = self._dialog("save", file_types=("CSV (*.csv)",), save_name=default_name)
        if not paths:
            return self.get_state()
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
        Path(paths[0]).write_text(buf.getvalue(), encoding="utf-8-sig", newline="")
        return self._done(t("web.file_saved"))

    def save_report(self) -> dict:
        with self._lock:
            ia, ib = self._slot["A"], self._slot["B"]
            evals = self._evals()
            if ia not in evals or ib not in evals:
                return self._done()
            text = text_report(compare(evals[ia], evals[ib], self._weights()))
        paths = self._dialog("save", file_types=(t("web.text_files") + " (*.txt)",), save_name="comparaison.txt")
        if paths:
            Path(paths[0]).write_text(text, encoding="utf-8")
            return self._done(t("web.report_saved"))
        return self.get_state()

    def _auto_update_check(self) -> None:
        """Au plus un contrôle par jour, sans bloquer le démarrage."""
        now = time.time()
        if now - float(self._store.get("update_checked_at", 0)) < updates.INTERVAL:
            return
        found = updates.fetch_latest(__version__)
        if found is None:
            return
        with self._lock:
            self._store.set("update_checked_at", now)
            if updates.is_newer(found["version"], __version__):
                self._update = found

    def set_update_check(self, on: bool) -> dict:
        with self._lock:
            self._store.set("update_check", bool(on))
            if not on:
                self._update = None
            return self._done()

    def check_update(self) -> dict:
        """Contrôle demandé par l'utilisateur (bouton) : ignore le délai de 24 h."""
        found = updates.fetch_latest(__version__)
        with self._lock:
            if found is None:
                return self._done(t("web.update_failed"))
            self._store.set("update_checked_at", time.time())
            if updates.is_newer(found["version"], __version__):
                self._update = found
                return self._done(t("web.update_available", version=found["version"]))
            self._update = None
            return self._done(t("web.update_none", version=__version__))

    def open_update_page(self) -> dict:
        with self._lock:
            url = (self._update or {}).get("url", "")
            if url.startswith(updates.RELEASE_PREFIX):
                webbrowser.open(url)
            return self._done()

    def open_log_folder(self) -> dict:
        """Ouvre le dossier du journal d'erreurs dans l'Explorateur."""
        folder = log_path().parent
        with self._lock:
            if sys.platform == "win32" and folder.is_dir():
                os.startfile(folder)    # noqa: S606 - dossier de l'application, pas une entrée utilisateur
                return self._done()
            return self._done(t("web.log_at", path=log_path()))

    def pick_ffprobe(self) -> dict:
        paths = self._dialog("open", file_types=("ffprobe (ffprobe*.exe)", t("web.all_files") + " (*.*)"))
        with self._lock:
            if paths:
                self._store.set("ffprobe", paths[0])
            return self._done()


def _guarded(name: str, fn):
    """Une erreur inattendue du moteur est écrite au journal et renvoyée à l'écran avec son vrai message."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - dernier filet : rien ne doit planter l'interface
            log.exception("Erreur dans %s", name)
            return {"error": t("web.internal_error", kind=type(exc).__name__, msg=exc)}
    return wrapper


for _name, _fn in list(vars(Api).items()):
    if not _name.startswith("_") and callable(_fn):
        setattr(Api, _name, _guarded(_name, _fn))


# ====================================================================== lancement
def run() -> None:
    import webview
    api = Api()
    window = webview.create_window("VidCompare", url=str(ui_dir() / "index.html"), js_api=api,
                                   width=1360, height=900, min_size=(980, 640), background_color="#0b0d11")
    api._attach(window)
    webview.start()


def run_dev(port: int = 5174) -> None:
    """Sert l'interface et l'API en HTTP local pour la tester dans un navigateur."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    api = Api()
    root = ui_dir()
    types = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            p = root / (self.path.split("?")[0].lstrip("/") or "index.html")
            if p.is_file() and root in p.resolve().parents:
                body = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", types.get(p.suffix, "application/octet-stream"))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def do_POST(self):
            name = self.path.removeprefix("/api/")
            fn = getattr(api, name, None) if not name.startswith("_") else None
            args = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "[]")
            try:
                out = fn(*args) if callable(fn) else {"error": f"unknown method: {name}"}
            except Exception as exc:  # noqa: BLE001
                out = {"error": str(exc)}
            body = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    print(f"Interface de développement : http://127.0.0.1:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    run_dev() if "--dev" in sys.argv else run()
