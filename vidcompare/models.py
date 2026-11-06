"""Structures de données partagées par tous les modules."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AudioTrack:
    index: int
    codec: str               # codec_name brut de ffprobe
    label: str               # clé de la matrice, ex. "TrueHD Atmos"
    channels: int
    bitrate: int | None      # bits/s
    language: str | None
    title: str | None
    lossless: bool


@dataclass
class MediaInfo:
    path: str
    filename: str
    size_bytes: int = 0
    duration: float | None = None
    container: str | None = None
    video_codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    bit_depth: int | None = None
    video_bitrate: int | None = None          # bits/s
    video_bitrate_estimated: bool = False
    hdr: str | None = None                    # clé de HDR_SCORES
    hdr10plus: bool = False
    audio: list[AudioTrack] = field(default_factory=list)
    subtitle_langs: list[str] = field(default_factory=list)
    partial: bool = False                     # analyse détaillée impossible (ISO)
    from_name: bool = False                   # estimé d'après un nom de torrent, fichier non lu
    claims: object | None = None              # NameClaims déjà fusionnés (torrents)
    notes: list[str] = field(default_factory=list)


@dataclass
class Warn:
    level: str               # "alert" | "warn" | "info"
    text: str


@dataclass
class SourceResolution:
    label: str               # clé de SOURCE_SCORES
    origin: str              # "nom du fichier" | "déduit du débit" | ...
    issues: list[str] = field(default_factory=list)


@dataclass
class CategoryResult:
    key: str
    label: str
    value: str
    score: int | None        # None = non évaluable
    detail: str = ""


@dataclass
class Evaluation:
    info: MediaInfo
    source: SourceResolution
    cats: dict[str, CategoryResult]
    warnings: list[Warn]
    adjusts: list = field(default_factory=list)   # (clé, libellé, points, détail) : groupe, langue...

    @property
    def adjust(self) -> float:
        """Total des points ajoutés ou retirés à la note, hors critères."""
        return sum(a[2] for a in self.adjusts)


@dataclass
class Contribution:
    key: str
    label: str
    a: CategoryResult
    b: CategoryResult
    points: float            # > 0 : avantage A, < 0 : avantage B


@dataclass
class Comparison:
    a: Evaluation
    b: Evaluation
    total_a: float
    total_b: float
    contributions: list[Contribution]
    winner: str              # "A" | "B" | "égalité"
    partial: bool
