"""Recherche de mise à jour : une seule requête HTTPS vers l'API publique de GitHub.

Rien n'est envoyé à part la requête elle-même (adresse IP et nom du programme dans User-Agent).
Désactivable dans les Réglages. Toute erreur réseau est ignorée : l'application ne dépend jamais de ce contrôle.
"""
from __future__ import annotations

import json
import re
import urllib.request

REPO = "BixSopy/VidCompare"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASE_PREFIX = f"https://github.com/{REPO}/"
INTERVAL = 24 * 3600          # secondes entre deux contrôles automatiques


def parse_version(text: str) -> tuple[int, ...] | None:
    m = re.match(r"^v?(\d+(?:\.\d+){0,3})", (text or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def fetch_latest(current: str, timeout: float = 5.0) -> dict | None:
    """{'version', 'url'} de la dernière version publiée, ou None si le contrôle échoue."""
    req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": f"VidCompare/{current}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:     # noqa: S310 - URL fixe en https
            data = json.loads(r.read(200_000).decode("utf-8"))
    except (OSError, ValueError):
        return None
    tag, url = str(data.get("tag_name", "")), str(data.get("html_url", ""))
    if not parse_version(tag) or not url.startswith(RELEASE_PREFIX):
        return None
    return {"version": tag.lstrip("v"), "url": url}
