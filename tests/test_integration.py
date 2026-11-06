"""Essais avec un vrai FFmpeg : ignorés si FFmpeg n'est pas installé."""
import subprocess
import time
from pathlib import Path

import pytest

from vidcompare import probe, vmaf
from vidcompare.cache import Cache
from vidcompare.history import History
from vidcompare.webapp import Api, Store

FFPROBE = probe.find_ffprobe()
FFMPEG = vmaf.find_ffmpeg()
pytestmark = pytest.mark.skipif(not (FFPROBE and FFMPEG), reason="FFmpeg (ffmpeg et ffprobe) introuvable")


def make_clip(path: Path, seconds: int, size="320x180", hdr=False, audio=True) -> str:
    cmd = [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=24:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=duration={seconds}"]
    if hdr:
        cmd += ["-vf", "format=yuv420p10le", "-c:v", "libx265", "-preset", "ultrafast", "-x265-params",
                "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:log-level=error", "-pix_fmt", "yuv420p10le"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-b:v", "1M"]
    if audio:
        cmd += ["-c:a", "eac3", "-ac", "6", "-metadata:s:a:0", "language=fra"]
    subprocess.run(cmd + [str(path)], check=True)
    return str(path)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    return {"sdr": make_clip(d / "Film.2024.1080p.WEB-DL.mkv", 5), "short": make_clip(d / "Film.2024.720p.HDTV.mkv", 4),
            "long": make_clip(d / "Film.Longue.2024.mkv", 75), "hdr": make_clip(d / "hdr.mkv", 3, "640x360", hdr=True, audio=False)}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return Api(Store(tmp_path / "r.json"), History(tmp_path / "h.json"), Cache(tmp_path / "c.json"))


def wait(cond, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.1)
    return False


def count_calls(monkeypatch):
    calls = []
    real = probe._run
    monkeypatch.setattr(probe, "_run", lambda cmd: (calls.append(cmd), real(cmd))[1])
    return calls


def test_real_probe_uses_one_call_for_sdr_and_two_for_hdr(clips, monkeypatch):
    calls = count_calls(monkeypatch)
    sdr = probe.load_media(clips["sdr"])
    assert len(calls) == 1 and sdr.hdr == "SDR" and sdr.video_codec == "h264"
    assert sdr.audio[0].label == "DD+" and sdr.audio[0].language == "fra" and sdr.duration == pytest.approx(5, abs=0.3)
    calls.clear()
    hdr = probe.load_media(clips["hdr"])
    assert len(calls) == 2 and hdr.hdr == "HDR10" and hdr.bit_depth == 10


def test_two_real_files_compare_and_guard_is_quiet(api, clips):
    api.set_source("A", clips["sdr"])
    api.set_source("B", clips["short"])
    assert wait(lambda: api.get_state()["result"] is not None)
    r = api.get_state()["result"]
    assert r["winner"] in {"A", "B"} and r["visual"]["available"] and not r["versionsBlock"]


def test_frames_are_parallel_and_cached(api, clips):
    api.set_source("A", clips["sdr"])
    api.set_source("B", clips["short"])
    assert wait(lambda: api.get_state()["result"] is not None)
    t0 = time.time()
    first = api.show_frames()
    t1 = time.time() - t0
    assert first["ok"] and len(first["frames"]) >= 1 and first["frames"][0]["src"].startswith("data:image/png;base64,")
    n = len(api._frames_cache)
    t0 = time.time()
    second = api.show_frames()
    assert second["ok"] and len(api._frames_cache) == n and time.time() - t0 < max(0.5, t1 / 2)


def test_different_cuts_are_flagged_before_vmaf(api, clips):
    api.set_source("A", clips["long"])
    api.set_source("B", clips["sdr"])
    assert wait(lambda: api.get_state()["result"] is not None)
    r = api.get_state()["result"]
    assert r["versionsBlock"] and r["versions"][0]["level"] == "alert" and "Durées différentes" in r["versions"][0]["text"]


def test_vmaf_end_to_end(api, clips):
    api.set_source("A", clips["sdr"])
    api.set_source("B", clips["sdr"])
    assert wait(lambda: api.get_state()["result"] is not None)
    api.run_vmaf()
    assert wait(lambda: "ressemble" in api.get_state()["result"]["visual"]["text"], 180)
    text = api.get_state()["result"]["visual"]["text"]
    assert "100" in text or "99" in text
