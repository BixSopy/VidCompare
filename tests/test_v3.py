from datetime import datetime

import pytest

from helpers import audio, make, video
from vidcompare import groups
from vidcompare.history import History
from vidcompare.mediainfo import MediaInfoError, parse_mediainfo
from vidcompare.parse_name import parse_name
from vidcompare.scoring import compare, evaluate, total_score
from vidcompare.torrent import parse_magnet, torrent_to_media
from vidcompare.vmaf import describe, sample_times

SDR = dict(transfer="bt709", pix="yuv420p")


def film(name, langs=("fra",), subs=()):
    info = make(name, [video(bit_rate=58_000_000, dv=(7, 6))] +
                [audio("truehd", 8, "Dolby TrueHD + Dolby Atmos", lang=l) for l in langs], 55)
    info.subtitle_langs = list(subs)
    return info


# --- 8 : préférence de langue -------------------------------------------------

def test_language_penalty_only_when_wanted():
    vo = film("Film.2160p.REMUX.mkv", langs=("eng",))
    assert total_score(evaluate(vo)) == total_score(evaluate(vo, lang="none"))
    plain, any_fr, fr_only = (evaluate(vo, lang=m) for m in ("none", "fr_any", "fr_audio"))
    assert total_score(any_fr) == pytest.approx(total_score(plain) - 5)
    assert total_score(fr_only) == pytest.approx(total_score(plain) - 8)


def test_french_subtitles_satisfy_fr_any_but_not_fr_audio():
    vo_st = film("Film.2160p.REMUX.mkv", langs=("eng",), subs=("fra",))
    assert total_score(evaluate(vo_st, lang="fr_any")) == total_score(evaluate(vo_st))
    assert total_score(evaluate(vo_st, lang="fr_audio")) < total_score(evaluate(vo_st))


def test_fr_audio_scores_the_french_track_not_the_original():
    both = make("Film.2160p.REMUX.mkv", [video(bit_rate=58_000_000, dv=(7, 6)),
                                          audio("truehd", 8, "Dolby TrueHD + Dolby Atmos", lang="eng"),
                                          audio("ac3", 6, lang="fra", bit_rate=640_000)], 55)
    assert evaluate(both).cats["audio"].score == 100
    ev = evaluate(both, lang="fr_audio")
    assert ev.cats["audio"].score < 60 and "AC3" in ev.cats["audio"].value


def test_language_row_appears_in_comparison():
    vf = film("Film.2160p.REMUX.mkv", langs=("fra",))
    vo = film("Film.2160p.REMUX.mkv", langs=("eng",))
    cmp = compare(evaluate(vf, lang="fr_audio"), evaluate(vo, lang="fr_audio"))
    row = next(c for c in cmp.contributions if c.key == "lang")
    assert row.points == pytest.approx(8) and cmp.winner == "A"


def test_french_tokens_in_release_names():
    assert "fr_audio" in parse_name("Film.2024.MULTi.1080p.WEB.x264-GRP.mkv").langs
    assert "fr_audio" in parse_name("Film.2024.TRUEFRENCH.1080p.mkv").langs
    assert "fr_sub" in parse_name("Film.2024.VOSTFR.1080p.mkv").langs
    assert not parse_name("Film.2024.1080p.WEB-DL.mkv").langs


def test_torrent_language_from_name():
    multi = evaluate(torrent_to_media(parse_magnet("magnet:?dn=Film.2024.MULTi.1080p.WEB.x264-GRP&xl=6000000000")),
                     lang="fr_audio")
    plain = evaluate(torrent_to_media(parse_magnet("magnet:?dn=Film.2024.1080p.WEB.x264-GRP&xl=6000000000")),
                     lang="fr_audio")
    assert total_score(multi) > total_score(plain)
    assert any("nom" in a[3] for a in plain.adjusts)


# --- 9 : réputation des groupes ----------------------------------------------------

def test_groups_save_load_and_clamp(tmp_path):
    p = tmp_path / "groupes.json"
    groups.save({"BonGroupe": 4, "Mauvais": -50, " ": 3}, p)
    data = groups.load(p)
    assert data == {"BonGroupe": 4.0, "Mauvais": -10.0}
    assert groups.load(tmp_path / "absent.json") == {}
    p.write_text("pas du json", encoding="utf-8")
    assert groups.load(p) == {}


# --- 12 : historique -------------------------------------------------------------------

def test_history_records_updates_and_removes(tmp_path):
    h = History(tmp_path / "h.json")
    a = {"name": "A.mkv", "source": "C:/a.mkv", "score": 90.0}
    b = {"name": "B.mkv", "source": "C:/b.mkv", "score": 60.0}
    h.record(a, b, "A", "Équilibré", datetime(2026, 11, 1, 10, 0))
    h.record(a, {**b, "score": 70.0}, "A", "Home cinéma", datetime(2026, 11, 2, 9, 0))   # même paire : mise à jour
    assert len(h.entries) == 1 and h.entries[0]["b"]["score"] == 70.0 and h.entries[0]["date"] == "2026-11-02 09:00"
    h.record(b, a, "A", "Équilibré")
    assert len(h.entries) == 2 and h.newest_first()[0][1]["a"]["name"] == "B.mkv"
    assert len(History(tmp_path / "h.json").entries) == 2          # relu depuis le disque
    h.remove([0])
    assert len(h.entries) == 1 and h.rows()[0]["fichier_a"] == "B.mkv"
    h.clear()
    assert History(tmp_path / "h.json").entries == []


# --- 10 : rapport MediaInfo --------------------------------------------------------------

REPORT_EN = """General
Unique ID                                : 1
Complete name                            : D:\\Films\\Film.2024.2160p.UHD.BluRay.REMUX.DV.HDR10.TrueHD.Atmos.7.1-GRP.mkv
Format                                   : Matroska
File size                                : 55.2 GiB
Duration                                 : 2 h 1 min
Overall bit rate                         : 65.3 Mb/s

Video
ID                                       : 1
Format                                   : HEVC
Format/Info                              : High Efficiency Video Coding
HDR format                               : Dolby Vision, Version 1.0, Profile 7.6, dvhe.07.06, BL+EL+RPU, no metadata compression / SMPTE ST 2086, HDR10 compatible
Bit rate                                 : 58.0 Mb/s
Width                                    : 3 840 pixels
Height                                   : 2 160 pixels
Frame rate                               : 23.976 (24000/1001) FPS
Bit depth                                : 10 bits

Audio #1
Format                                   : MLP FBA
Commercial name                          : Dolby TrueHD with Dolby Atmos
Bit rate                                 : 4 500 kb/s
Channel(s)                               : 8 channels
Language                                 : English

Audio #2
Format                                   : AC-3
Commercial name                          : Dolby Digital
Bit rate                                 : 640 kb/s
Channel(s)                               : 6 channels
Language                                 : French

Text #1
Language                                 : French
"""

REPORT_FR = """Général
Nom complet                              : Film.2024.1080p.WEB-DL.DDP5.1.x265-GRP.mkv
Format                                   : Matroska
Taille du fichier                        : 6,02 Gio
Durée                                    : 1 h 58 min
Débit global                             : 7 289 kb/s

Vidéo
Format                                   : HEVC
Largeur                                  : 1 920 pixels
Hauteur                                  : 1 080 pixels
Fréquence d’image                        : 23,976 images/s
Profondeur de bit                        : 10 bits

Audio
Format                                   : E-AC-3
Nom commercial                           : Dolby Digital Plus avec Dolby Atmos
Débit                                    : 768 kb/s
Canaux                                   : 6 canaux
Langue                                   : Français
"""


def test_mediainfo_english_report():
    info = parse_mediainfo(REPORT_EN)
    assert info.filename.startswith("Film.2024.2160p") and info.size_bytes == int(55.2 * 1024 ** 3)
    assert (info.video_codec, info.width, info.height, info.bit_depth) == ("hevc", 3840, 2160, 10)
    assert info.hdr == "DV P7" and info.video_bitrate == 58_000_000 and info.duration == 7260
    assert [t.label for t in info.audio] == ["TrueHD Atmos", "AC3"]
    assert info.audio[0].channels == 8 and info.audio[1].language == "fr" and info.subtitle_langs == ["fr"]
    ev = evaluate(info)
    assert ev.source.label == "Remux" and ev.cats["hdr"].score == 100 and not ev.info.from_name


def test_mediainfo_french_report_estimates_missing_video_bitrate():
    info = parse_mediainfo(REPORT_FR)
    assert info.hdr == "SDR" and info.audio[0].label == "DD+ Atmos" and info.audio[0].language == "fr"
    assert info.video_bitrate == 7_289_000 - 768_000 and info.video_bitrate_estimated
    assert (info.width, info.height, round(info.fps, 2)) == (1920, 1080, 23.98)


def test_mediainfo_rejects_garbage():
    with pytest.raises(MediaInfoError):
        parse_mediainfo("ceci n'est pas un rapport")


# --- 14 : échantillons VMAF ------------------------------------------------------------------

def test_sample_times():
    t = sample_times(7200, 7100)
    assert len(t) == 3 and t == sorted(t) and t[0] > 1000 and t[-1] < 7100 - 8
    short = sample_times(20, 30)
    assert len(short) == 1 and 0 <= short[0] <= 20
    assert sample_times(None, None) == [0.0]


@pytest.mark.parametrize("score,text", [(97, "quasi indiscernable"), (92, "différences à peine visibles"),
                                        (85, "différences visibles"), (60, "nettement dégradé")])
def test_vmaf_description(score, text):
    assert describe(score) == text
