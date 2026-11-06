"""Compatibilité avec le matériel de lecture : ce que l'écran et l'ampli savent lire."""
from __future__ import annotations

from dataclasses import asdict, dataclass

DTS_FAMILY = {"DTS", "DTS-HD MA", "DTS-HD HRA", "DTS:X"}
TRUEHD_FAMILY = {"TrueHD", "TrueHD Atmos"}


@dataclass
class Device:
    dv: bool = True            # Dolby Vision
    hdr10plus: bool = True
    hdr: bool = True           # HDR10 et HLG
    max_res: str = "2160p"     # "2160p" ou "1080p"
    dts: bool = True
    truehd: bool = True
    atmos: bool = True
    hevc: bool = True
    av1: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


# Exemples de départ, à ajuster selon votre modèle exact.
PRESETS: dict[str, Device] = {
    "Sans contrainte": Device(),
    "TV 4K Samsung (HDR10+, sans Dolby Vision ni DTS)": Device(dv=False, dts=False, truehd=False, atmos=False),
    "TV 4K LG OLED (Dolby Vision, sans HDR10+ ni DTS)": Device(hdr10plus=False, dts=False, truehd=False),
    "TV Full HD sans HDR": Device(dv=False, hdr10plus=False, hdr=False, max_res="1080p", av1=False),
}


def effective_hdr(label: str, dev: Device | None):
    """Renvoie (clé pour la note, texte affiché, note forcée ou None)."""
    if dev is None:
        return label, label, None
    shown = label
    if label.startswith("DV") and not dev.dv:
        if label in ("DV P7", "DV P8.1"):
            label = "HDR10"
        elif label == "DV P8.4":
            label = "HLG"
        else:
            return "SDR", f"{label} (illisible sur votre écran)", 15
    if label == "HDR10+" and not dev.hdr10plus:
        label = "HDR10"
    if label in ("HDR10", "HLG") and not dev.hdr:
        label = "SDR"
    if label != shown:
        shown = f"{shown} → lu en {label}"
    return label, shown, None


def effective_audio(label: str, dev: Device | None) -> str | None:
    """Renvoie la piste telle que votre matériel la lit, ou None si elle est illisible."""
    if dev is None:
        return label
    if label in DTS_FAMILY and not dev.dts:
        return None
    if label in TRUEHD_FAMILY and not dev.truehd:
        return None
    if label in ("TrueHD Atmos", "DD+ Atmos") and not dev.atmos:
        label = label.replace(" Atmos", "")
    return label
