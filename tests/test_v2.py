import pytest

from helpers import audio, make, video
from vidcompare import groups
from vidcompare.device import PRESETS, Device
from vidcompare.report import ranking_rows, size_line
from vidcompare.scoring import PROFILES, compare, evaluate, rank, total_score
from vidcompare.torrent import (TorrentError, parse_magnet, parse_torrent_bytes,
                                torrent_to_media)

GB = 1_000_000_000


def benc(v):
    if isinstance(v, int):
        return b"i%de" % v
    if isinstance(v, str):
        v = v.encode()
    if isinstance(v, bytes):
        return b"%d:%s" % (len(v), v)
    if isinstance(v, list):
        return b"l" + b"".join(benc(x) for x in v) + b"e"
    return b"d" + b"".join(benc(k) + benc(v[k]) for k in sorted(v)) + b"e"


def torrent(name, size_gb, extra_files=()):
    files = [{"length": int(size_gb * GB), "path": [name + ".mkv"]}] + [
        {"length": s, "path": [n]} for n, s in extra_files]
    return benc({"announce": "http://tracker.example/a", "info": {"name": name, "files": files}})


REMUX = "Film.2024.2160p.UHD.BluRay.REMUX.DV.HDR10.HEVC.TrueHD.Atmos.7.1-GRP"


def test_torrent_parsing():
    t = parse_torrent_bytes(torrent(REMUX, 55, [("readme.txt", 100)]))
    assert t.name == REMUX and t.trackers == ["http://tracker.example/a"]
    assert t.main_file()[0].endswith(".mkv") and t.total > 55 * GB


def test_invalid_torrent():
    with pytest.raises(TorrentError):
        parse_torrent_bytes(b"ceci n'est pas un torrent")
    with pytest.raises(TorrentError):
        parse_torrent_bytes(b"d3:fooi1ee")


def test_magnet():
    m = parse_magnet("magnet:?xt=urn:btih:abc&dn=Film.2024.1080p.WEB-DL.DDP5.1-GRP&xl=6000000000&tr=udp%3A%2F%2Ft")
    assert m.name.startswith("Film.2024") and m.total == 6 * GB and m.trackers == ["udp://t"]
    with pytest.raises(TorrentError):
        parse_magnet("magnet:?xt=urn:btih:abc")
    with pytest.raises(TorrentError):
        parse_magnet("http://exemple.fr")


def test_torrent_estimation_from_name_and_size():
    ev = evaluate(torrent_to_media(parse_torrent_bytes(torrent(REMUX, 55))))
    assert ev.info.from_name and ev.source.label == "Remux"
    assert ev.cats["hdr"].value == "DV P7" and ev.cats["audio"].value.startswith("TrueHD Atmos")
    assert "estimé" in ev.cats["bitrate"].value
    assert total_score(ev) > 90


def test_fake_remux_torrent_is_caught_by_size():
    ev = evaluate(torrent_to_media(parse_torrent_bytes(torrent(REMUX, 12))))
    assert ev.source.label != "Remux"
    assert any(w.level == "alert" and "remux" in w.text.lower() for w in ev.warnings)


def test_magnet_without_size_still_scores():
    ev = evaluate(torrent_to_media(parse_magnet("magnet:?dn=Film.2024.1080p.WEB-DL.DDP5.1.H.264-GRP")))
    assert ev.cats["bitrate"].score is None and ev.cats["source"].label == "Source"
    assert total_score(ev) is not None


def test_torrent_vs_local_file_comparison():
    t = evaluate(torrent_to_media(parse_torrent_bytes(torrent("Film.2024.1080p.WEB-DL.DDP5.1.H.264-GRP", 6))))
    f = evaluate(make("Film.2024.2160p.REMUX.DV.mkv", [video(bit_rate=58_000_000, dv=(7, 6)), audio("truehd", 8)]))
    cmp = compare(f, t)
    assert cmp.winner == "A" and cmp.partial


def uhd_dv_dts():
    return make("Film.2024.2160p.REMUX.mkv",
                [video(bit_rate=58_000_000, dv=(7, 6)),
                 audio("dts", 8, "DTS-HD MA + DTS:X", lang="eng"),
                 audio("eac3", 6, bit_rate=640_000, lang="fra")], size_gb=55)


def test_device_without_dolby_vision_and_dts():
    free = evaluate(uhd_dv_dts())
    tv = evaluate(uhd_dv_dts(), device=PRESETS["TV 4K Samsung (HDR10+, sans Dolby Vision ni DTS)"])
    assert "lu en HDR10" in tv.cats["hdr"].value and tv.cats["hdr"].score == 78
    assert tv.cats["audio"].score < free.cats["audio"].score
    assert tv.cats["audio"].value.startswith("DD+")
    assert total_score(tv) < total_score(free)


def test_device_1080p_screen_caps_resolution_and_no_audio_case():
    dev = Device(max_res="1080p", dts=False, truehd=False)
    ev = evaluate(make("a.mkv", [video(), audio("dts", 6, "DTS-HD MA")]), device=dev)
    assert ev.cats["resolution"].score == 72 and "1080p" in ev.cats["resolution"].value
    assert ev.cats["audio"].score == 10 and any("lisible" in w.text for w in ev.warnings)


def test_dv_profile5_unreadable_without_dv():
    ev = evaluate(make("a.mkv", [video(dv=(5, 0)), audio("eac3", 6)]), device=Device(dv=False))
    assert ev.cats["hdr"].score == 15 and "illisible" in ev.cats["hdr"].value


def test_hevc_unsupported_device_penalises_codec():
    ev = evaluate(make("a.mkv", [video(), audio("eac3", 6)]), device=Device(hevc=False))
    assert ev.cats["codec"].score == 20


def test_ranking_is_sorted_and_exports_rows():
    a = evaluate(uhd_dv_dts())
    b = evaluate(make("Film.1080p.WEB-DL.mkv", [video(1920, 1080, "h264", bit_rate=6_000_000,
                                                      transfer="bt709", pix="yuv420p"), audio("eac3", 6)], 6))
    c = evaluate(make("Film.480p.DVDRip.avi", [video(720, 480, "mpeg4", bit_rate=1_000_000,
                                                     transfer="bt709", pix="yuv420p"), audio("mp3", 2)], 1.4))
    ranked = rank([c, b, a])
    assert [r[0] for r in ranked] == [a, b, c]
    rows = ranking_rows(ranked)
    assert [r["rang"] for r in rows] == [1, 2, 3] and rows[0]["note"] > rows[1]["note"] > rows[2]["note"]


def test_size_line_is_honest_about_value():
    big = evaluate(uhd_dv_dts())
    small = evaluate(make("Film.1080p.WEB-DL.mkv", [video(1920, 1080, "h264", bit_rate=6_000_000,
                                                          transfer="bt709", pix="yuv420p"), audio("eac3", 6)], 6))
    line = size_line(compare(big, small))
    assert "pt par Go" in line and "A pèse" in line
    assert size_line(compare(big, big)) is None


def test_group_bonus_changes_score(monkeypatch):
    monkeypatch.setattr(groups, "bonuses", lambda: {"grp": 5.0})
    named = evaluate(make("Film.2024.1080p.WEB-DL.DDP5.1.H.264-GRP.mkv",
                          [video(1920, 1080, "h264", bit_rate=6_000_000, transfer="bt709", pix="yuv420p"),
                           audio("eac3", 6)], 6))
    plain = evaluate(make("Film.2024.1080p.WEB-DL.DDP5.1.H.264-AUTRE.mkv",
                          [video(1920, 1080, "h264", bit_rate=6_000_000, transfer="bt709", pix="yuv420p"),
                           audio("eac3", 6)], 6))
    cmp = compare(named, plain, PROFILES["Équilibré"])
    assert abs((cmp.total_a - cmp.total_b) - 5.0) < 1e-6
    assert any(c.key == "group" for c in cmp.contributions)


def test_french_audio_warning():
    ev = evaluate(uhd_dv_dts(), lang="any")
    assert not any("Ni piste audio ni sous-titres" in w.text for w in ev.warnings)
    none = evaluate(make("a.mkv", [video(), audio("eac3", 6, lang="eng")]), lang="any")
    assert any("Ni piste audio ni sous-titres" in w.text for w in none.warnings)
    off = evaluate(make("a.mkv", [video(), audio("eac3", 6, lang="eng")]))
    assert not any("Ni piste audio ni sous-titres" in w.text for w in off.warnings)
