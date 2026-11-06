import json

import pytest

from helpers import audio, make, video
from vidcompare.cache import Cache, info_from_dict, info_to_dict
from vidcompare.device import Device
from vidcompare.parse_name import parse_name
from vidcompare.scoring import evaluate
from vidcompare.upgrades import (LEVELS, MIN_GAIN, build_suggestions, classify, suggestion_rows,
                                 target_parts, wanted_text)

SDR = dict(transfer="bt709", pix="yuv420p")


def web1080(path, gb=4.0):
    return evaluate(make(path, [video(1920, 1080, "h264", bit_rate=5_000_000, **SDR),
                                audio("eac3", 6, bit_rate=640_000, lang="fra")], gb))


def top4k(path):
    return evaluate(make(path, [video(bit_rate=58_000_000, dv=(7, 6)),
                                audio("truehd", 8, "Dolby TrueHD + Dolby Atmos", "fra")], 55))


@pytest.mark.parametrize("name,title,season,episode", [
    ("Le.Parrain.1972.1080p.BluRay.x264-GRP.mkv", "Le Parrain", None, None),
    ("Breaking.Bad.S02E05.1080p.WEB-DL.mkv", "Breaking Bad", 2, 5),
    ("The Show 3x07 720p HDTV.mkv", "The Show", 3, 7),
    ("Show.Name.S04.2160p.WEB-DL.mkv", "Show Name", 4, None),
    ("2012.2009.1080p.BluRay.mkv", "2012", None, None),
])
def test_title_and_season(name, title, season, episode):
    c = parse_name(name)
    assert (c.title, c.season, c.episode) == (title, season, episode)


def test_classify_uses_folders_for_bare_episode_names():
    kind, title, season = classify("D:/Series/The Wire/Saison 2/S02E03.mkv", parse_name("S02E03.mkv"))
    assert (kind, title, season) == ("Série", "The Wire", 2)
    kind, title, _ = classify("D:/Films/Heat.1995.1080p.mkv", parse_name("Heat.1995.1080p.mkv"))
    assert (kind, title) == ("Film", "Heat")


def test_films_and_series_are_separated_and_sorted_by_gain():
    evals = [
        web1080("D:/Films/Alien.1979.1080p.WEB-DL.mkv"),
        evaluate(make("D:/Films/Dune.2021.1080p.BluRay.mkv", [video(1920, 1080, "h264", bit_rate=25_000_000, **SDR),
                                                              audio("dts", 6, "DTS-HD MA")], 20)),
        top4k("D:/Films/Avatar.2009.2160p.REMUX.mkv"),
        web1080("D:/Series/Lost/Saison 1/Lost.S01E01.1080p.WEB-DL.mkv"),
        web1080("D:/Series/Lost/Saison 1/Lost.S01E02.1080p.WEB-DL.mkv"),
        web1080("D:/Series/Lost/Saison 2/Lost.S02E01.1080p.WEB-DL.mkv"),
    ]
    films, series, ok, total = build_suggestions(evals)
    assert total == 6 and ok == 1                       # Avatar est déjà au sommet
    assert [f.title for f in films] == ["Alien", "Dune"]  # le plus gros gain en premier
    assert films[0].gain > films[1].gain > MIN_GAIN
    assert [(s.title, s.season, s.files) for s in series] == [("Lost", 1, 2), ("Lost", 2, 1)] or \
           [(s.title, s.season, s.files) for s in series] == [("Lost", 2, 1), ("Lost", 1, 2)]
    assert all(s.kind == "Série" for s in series) and "épisodes" in max(series, key=lambda s: s.files).display


def test_improvements_name_the_biggest_gaps_first():
    films, _, _, _ = build_suggestions([web1080("D:/Films/Alien.1979.1080p.WEB-DL.mkv")])
    f = films[0]
    assert f.improvements[0].label == "HDR" and f.improvements[0].now == "SDR"
    assert "DV P7" in f.improvements[0].wanted
    assert f.target > f.current and abs(f.target - f.current - f.gain) < 1e-9
    assert "2160p" in f.wanted and "Remux" in f.wanted


def test_device_limits_what_is_worth_looking_for():
    ev = web1080("D:/Films/Alien.1979.1080p.WEB-DL.mkv")
    free = target_parts(LEVELS["Le meilleur possible (4K Remux)"], None)
    tv = target_parts(LEVELS["Le meilleur possible (4K Remux)"], Device(dv=False, dts=False, truehd=False,
                                                                       max_res="1080p"))
    assert free["hdr"].text == "DV P7" and tv["hdr"].text == "HDR10"
    assert tv["audio"].text == "DD+ Atmos" and tv["resolution"].text == "1080p"
    g_free = build_suggestions([ev])[0][0].gain
    g_tv = build_suggestions([ev], dev=Device(dv=False, dts=False, truehd=False, max_res="1080p"))[0][0].gain
    assert g_tv < g_free
    assert "1080p" in wanted_text(tv)


def test_lower_level_asks_for_less():
    bluray = evaluate(make("Dune.2021.1080p.BluRay.mkv", [video(1920, 1080, "h264", bit_rate=25_000_000, **SDR),
                                                          audio("dts", 6, "DTS-HD MA")], 20))
    top = build_suggestions([bluray], level_name="Le meilleur possible (4K Remux)")[0][0].gain
    ok = build_suggestions([bluray], level_name="Correct (1080p BluRay)")
    assert not ok[0] and ok[2] == 1                      # un bon BluRay 1080p n'a rien à gagner à ce niveau
    assert top > 15
    web = web1080("D:/Films/Alien.1979.1080p.WEB-DL.mkv")
    assert build_suggestions([web], level_name="Correct (1080p BluRay)")[0][0].gain < \
        build_suggestions([web], level_name="Le meilleur possible (4K Remux)")[0][0].gain


def test_rows_for_csv():
    films, series, _, _ = build_suggestions([web1080("D:/Films/Alien.1979.1080p.WEB-DL.mkv"),
                                             web1080("D:/Series/Lost/Lost.S01E01.1080p.WEB-DL.mkv")])
    rows = suggestion_rows(films, series)
    assert [r["type"] for r in rows] == ["Film", "Série"] and rows[0]["priorite"] == 1
    assert rows[0]["gain_possible"] > 0 and "Dolby" not in rows[0]["a_viser"]


def test_cache_roundtrip(tmp_path):
    media = tmp_path / "film.mkv"
    media.write_bytes(b"x" * 100)
    info = make("film.mkv", [video(bit_rate=58_000_000, dv=(7, 6)), audio("truehd", 8)])
    info.path = str(media)
    cache = Cache(tmp_path / "cache.json")
    assert cache.get(str(media)) is None
    cache.put(str(media), info)
    cache.save()
    again = Cache(tmp_path / "cache.json").get(str(media))
    assert again is not None and again.hdr == info.hdr and again.audio[0].label == "TrueHD"
    assert info_from_dict(json.loads(json.dumps(info_to_dict(info)))).video_bitrate == 58_000_000
    media.write_bytes(b"y" * 200)                        # fichier modifié : l'ancienne analyse ne vaut plus
    assert Cache(tmp_path / "cache.json").get(str(media)) is None
