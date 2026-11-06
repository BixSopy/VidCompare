import os
import tempfile
import time

import pytest

from helpers import audio, make, video
from vidcompare import probe
from vidcompare.cache import Cache, info_from_dict, info_to_dict
from vidcompare.history import History
from vidcompare.versions import compare_versions, fmt_duration, needs_confirmation
from vidcompare.webapp import Api, Store, log, log_path

SDR = dict(transfer="bt709", pix="yuv420p")


def clip(name, minutes=120, fps=23.976, w=1920, h=1080, chapters=()):
    info = make(name, [video(w, h, "h264", bit_rate=6_000_000, **SDR), audio("eac3", 6)], 5, minutes)
    info.fps = fps
    info.chapters = list(chapters)
    return info


# --- garde « mêmes versions » ----------------------------------------------------------

def test_same_cut_gives_no_alert():
    assert compare_versions(clip("a.mkv"), clip("b.mkv")) == []


def test_different_durations_ask_for_confirmation():
    issues = compare_versions(clip("a.mkv", 169), clip("b.mkv", 162))
    assert needs_confirmation(issues) and "montages différents" in issues[0].text
    assert "2 h 49 min" in issues[0].text and "2 h 42 min" in issues[0].text


def test_small_gap_is_only_informative():
    a, b = clip("a.mkv", 120), clip("b.mkv", 120)
    b.duration = a.duration + 20
    issues = compare_versions(a, b)
    assert [i.level for i in issues] == ["info"] and not needs_confirmation(issues)


def test_pal_speedup_is_recognised():
    issues = compare_versions(clip("a.mkv", fps=23.976), clip("b.mkv", fps=25.0))
    assert any("PAL" in i.text and i.level == "warn" for i in issues)


def test_aspect_ratio_and_chapters_differences():
    issues = compare_versions(clip("a.mkv", w=1920, h=800, chapters=[0, 600, 1200]), clip("b.mkv", chapters=[0, 600]))
    texts = " ".join(i.text for i in issues)
    assert "Format d'image différent" in texts and "chapitres" in texts


def test_guard_is_silent_without_real_files():
    a = clip("a.mkv", 169)
    b = clip("b.mkv", 100)
    b.from_name = True
    assert compare_versions(a, b) == []
    b.from_name, b.partial = False, True
    assert compare_versions(a, b) == []


@pytest.mark.parametrize("s,txt", [(7260, "2 h 01 min"), (2830, "47 min 10 s"), (42, "42 s")])
def test_duration_format(s, txt):
    assert fmt_duration(s) == txt


# --- un seul ffprobe pour les vidéos SDR ---------------------------------------------------

def fake_streams(transfer):
    return {"format": {"duration": "10"}, "streams": [{"codec_type": "video", "codec_name": "hevc", "width": 1920,
                                                       "height": 1080, "color_transfer": transfer}],
            "chapters": [{"start_time": "0.000000"}, {"start_time": "600.5"}]}


@pytest.mark.parametrize("transfer,calls", [("bt709", 1), (None, 1), ("arib-std-b67", 1), ("smpte2084", 2)])
def test_second_ffprobe_call_only_for_pq(monkeypatch, transfer, calls):
    seen = []

    def fake_run(cmd):
        seen.append(cmd)
        return {"frames": [{"side_data_list": []}]} if "-show_frames" in cmd else fake_streams(transfer)
    monkeypatch.setattr(probe, "_run", fake_run)
    monkeypatch.setattr(probe, "find_ffprobe", lambda custom=None: "ffprobe")
    data = probe.run_ffprobe("x.mkv")
    assert len(seen) == calls and "-show_chapters" in seen[0]
    assert ("_first_frame" in data) and bool(data["_first_frame"]) == (calls == 2)


def test_chapters_are_read():
    info = probe.parse_probe(fake_streams("bt709"), "x.mkv", 1000)
    assert info.chapters == [0.0, 600.5]
    assert info_from_dict(info_to_dict(info)).chapters == [0.0, 600.5]


# --- fiabilité : journal, nettoyage, pagination ----------------------------------------------

@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from vidcompare import groups
    groups.reload()
    return Api(Store(tmp_path / "r.json"), History(tmp_path / "h.json"), Cache(tmp_path / "c.json"))


def test_unexpected_error_is_returned_and_logged(api, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("panne simulée")
    monkeypatch.setattr(api, "_evals", boom)
    out = Api.get_state(api)
    assert "RuntimeError" in out["error"] and "panne simulée" in out["error"] and "journal" in out["error"]
    assert log.handlers and log_path().name == "vidcompare.log"


def test_state_carries_the_version(api):
    from vidcompare import __version__
    assert api.get_state()["version"] == __version__ == "6.1.0"


def test_old_temp_folders_are_swept(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    old, fresh, other = tmp_path / "vidcompare_old", tmp_path / "vidcompare_fresh", tmp_path / "autre_dossier"
    for d in (old, fresh, other):
        d.mkdir()
        (d / "x.png").write_bytes(b"x")
    past = time.time() - 7200
    os.utime(old, (past, past))
    os.utime(other, (past, past))
    Api(Store(tmp_path / "r.json"), History(tmp_path / "h.json"), Cache(tmp_path / "c.json"))
    assert not old.exists() and fresh.exists() and other.exists()      # seuls les anciens vidcompare_* partent


def test_upgrade_lists_are_paginated(api):
    infos = [make(f"D:/Films/Film{i:03}.2024.1080p.WEB-DL.mkv",
                  [video(1920, 1080, "h264", bit_rate=5_000_000, **SDR), audio("eac3", 6, bit_rate=640_000)], 4)
             for i in range(120)]
    api._up_infos, api._up_ver = infos, 1
    lib = api.get_state()["library"]
    assert len(lib["films"]) == 50 and lib["filmsTotal"] == 120
    assert len(api.up_more("films")["library"]["films"]) == 100
    assert len(api.up_more("films")["library"]["films"]) == 120 and len(api.up_more("films")["library"]["films"]) == 120
    api.up_set_level("Correct (1080p BluRay)")                   # changer de niveau repart de la première page
    assert len(api._up_limit) == 2 and api._up_limit["films"] == 50


def test_scan_and_interactive_work_use_separate_pools(api):
    assert api._pool is not api._scan_pool
    assert api._scan_pool._max_workers >= 1 and api._pool._max_workers >= 1
