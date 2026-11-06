"""Comparaison visuelle : images côte à côte et score VMAF (via FFmpeg).

VMAF mesure à quel point un fichier ressemble à un autre pris comme référence (0 à 100).
Ce n'est pas une qualité absolue : on prend le meilleur fichier comme référence et on mesure
l'écart de l'autre. Quelques extraits courts suffisent, et les deux vidéos sont ramenées à la
même taille et à la même cadence avant la mesure.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .i18n import t as tr      # « t » est déjà le nom d'un instant (en secondes) dans ce module
from .models import MediaInfo
from .probe import find_ffprobe

SAMPLES = 3            # nombre d'extraits
SAMPLE_SECONDS = 8     # durée de chaque extrait
FRAME_W, FRAME_H = 960, 540


class VmafError(RuntimeError):
    pass


def find_ffmpeg(ffprobe: str | None = None) -> str | None:
    probe = find_ffprobe(ffprobe)
    if probe:
        sib = Path(probe).with_name("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if sib.is_file():
            return str(sib)
    return shutil.which("ffmpeg")


def sample_times(dur_a: float | None, dur_b: float | None, n: int = SAMPLES, length: int = SAMPLE_SECONDS) -> list[float]:
    """Instants répartis dans la durée commune (20 %, 50 %, 80 %), sans dépasser la fin."""
    durations = [d for d in (dur_a, dur_b) if d]
    if not durations:
        return [0.0]
    d = min(durations)
    if d <= n * length * 1.5:
        return [max(0.0, d / 2 - length / 2)]
    marks = [0.2, 0.5, 0.8][:n] if n <= 3 else [i / (n + 1) for i in range(1, n + 1)]
    return [max(0.0, min(d * m - length / 2, d - length - 1)) for m in marks]


def _tonemap(info: MediaInfo | None) -> str:
    """Ramène le HDR vers du SDR pour que les images et la mesure soient comparables."""
    if info and info.hdr and info.hdr != "SDR":
        return ("zscale=t=linear:npl=100,format=gbrpf32le,tonemap=hable:desat=0,"
                "zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p,")
    return ""


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 600, what: str = "FFmpeg") -> subprocess.CompletedProcess:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=cwd, creationflags=flags, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise VmafError(tr("vm.timeout", what=what, min=timeout // 60)) from None
    if p.returncode != 0:
        tail = (p.stderr or "").strip().splitlines()[-3:]
        raise VmafError(f"{what} : " + (" ".join(tail) or tr("vm.failed")))
    return p


# Sans flux audio, sous-titres ni données : FFmpeg n'ouvre que la vidéo, ce qui compte sur un remux de 60 Go.
_VIDEO_ONLY = ["-an", "-sn", "-dn"]


def _frame(ffmpeg: str, info: MediaInfo, t: float, out: Path, label: str) -> Path:
    """Une image réduite à 960×540 (HDR converti en SDR). On réduit AVANT le HDR : bien moins de pixels à traiter."""
    graph = (f"scale={FRAME_W}:{FRAME_H}:force_original_aspect_ratio=decrease,{_tonemap(info)}"
             f"pad={FRAME_W}:{FRAME_H}:(ow-iw)/2:(oh-ih)/2")
    _run([ffmpeg, "-v", "error", "-y", "-ss", f"{t:.2f}", *_VIDEO_ONLY, "-i", info.path,
          "-vf", graph, "-frames:v", "1", str(out)], timeout=600, what=tr("vm.file", tag=label))
    if not out.is_file():
        raise VmafError(tr("vm.no_frame", tag=label))
    return out


def side_by_side(ffmpeg: str, a: MediaInfo, b: MediaInfo, t: float, out_png: Path) -> Path:
    """Une image par fichier au même instant, A à gauche et B à droite, dans un seul PNG.

    Les deux fichiers sont lus en parallèle, chacun avec sa propre commande : si l'un est lent,
    le message d'erreur dit lequel.
    """
    from concurrent.futures import ThreadPoolExecutor
    part_a, part_b = out_png.with_name(out_png.stem + "_a.png"), out_png.with_name(out_png.stem + "_b.png")
    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(_frame, ffmpeg, a, t, part_a, "A")
        fb = pool.submit(_frame, ffmpeg, b, t, part_b, "B")
        fa.result()
        fb.result()
    _run([ffmpeg, "-v", "error", "-y", "-i", str(part_a), "-i", str(part_b), "-filter_complex", "hstack",
          "-frames:v", "1", str(out_png)], timeout=60, what=tr("vm.assemble"))
    return out_png


def measure_vmaf(ffmpeg: str, ref: MediaInfo, dist: MediaInfo, times: list[float],
                 progress=None) -> float:
    """VMAF moyen de `dist` par rapport à `ref`, sur les extraits donnés."""
    w = min(ref.width or 1920, 1920)
    h = min(ref.height or 1080, 1080)
    w, h = w - w % 2, h - h % 2
    scores: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(times):
            log = f"vmaf{i}.json"

            def chain(info, label, fps=""):      # réduire d'abord, convertir le HDR ensuite
                return (f"[{label}:v]scale={w}:{h}:flags=bicubic,{_tonemap(info)}{fps}"
                        f"setpts=PTS-STARTPTS[v{label}]")
            # Bonne pratique VMAF : on adapte la cadence de la vidéo comparée à celle de la référence,
            # jamais l'inverse ni les deux.
            dist_fps = f"fps={ref.fps:.3f}," if ref.fps and dist.fps and abs(ref.fps - dist.fps) > 0.01 else ""
            graph = (f"{chain(dist, 0, dist_fps)};{chain(ref, 1)};"
                     f"[v0][v1]libvmaf=n_threads={os.cpu_count() or 4}:log_fmt=json:log_path={log}")
            _run([ffmpeg, "-v", "error", "-y", "-ss", f"{t:.2f}", "-t", str(SAMPLE_SECONDS), *_VIDEO_ONLY,
                  "-i", dist.path, "-ss", f"{t:.2f}", "-t", str(SAMPLE_SECONDS), *_VIDEO_ONLY, "-i", ref.path,
                  "-filter_complex", graph, "-f", "null", "-"], cwd=tmp, timeout=1500,
                 what=tr("vm.measure", n=i + 1))
            try:
                data = json.loads((Path(tmp) / log).read_text(encoding="utf-8"))
                scores.append(float(data["pooled_metrics"]["vmaf"]["mean"]))
            except (OSError, ValueError, KeyError) as exc:
                raise VmafError(tr("vm.unreadable")) from exc
            if progress:
                progress(i + 1, len(times))
    return sum(scores) / len(scores)


def describe(score: float) -> str:
    if score >= 95:
        return tr("vm.d_same")
    if score >= 90:
        return tr("vm.d_slight")
    if score >= 80:
        return tr("vm.d_visible")
    return tr("vm.d_bad")
