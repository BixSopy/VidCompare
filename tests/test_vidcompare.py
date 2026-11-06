import pytest

from helpers import audio, make, video
from vidcompare.metrics import bitrate_score, resolution_tier
from vidcompare.parse_name import parse_name
from vidcompare.probe import audio_label, classify_hdr
from vidcompare.report import explanations, verdict
from vidcompare.scoring import PROFILES, compare, evaluate

REMUX = "Film.2024.2160p.UHD.BluRay.REMUX.DV.HDR10.HEVC.TrueHD.Atmos.7.1-GRP.mkv"
WEB = "Film.2024.1080p.WEB-DL.DDP5.1.H.264-GRP.mkv"


def uhd_remux():
    return make(REMUX, [video(bit_rate=58_000_000, dv=(7, 6)),
                        audio("truehd", 8, "Dolby TrueHD + Dolby Atmos"),
                        audio("ac3", 6, bit_rate=640_000)], size_gb=55)


def web_1080():
    return make(WEB, [video(1920, 1080, "h264", bit_rate=6_000_000, transfer="bt709", pix="yuv420p"),
                      audio("eac3", 6, bit_rate=640_000)], size_gb=6)


def test_name_parsing_remux():
    c = parse_name(REMUX)
    assert c.source == "Remux" and c.resolution == "2160p" and c.codec == "hevc"
    assert c.hdr == {"DV", "HDR10"}
    assert "TrueHD Atmos" in c.audio and c.channels == "7.1" and c.group == "GRP" and c.year == 2024


def test_name_parsing_web():
    c = parse_name(WEB)
    assert (c.source, c.resolution, c.codec) == ("WEB-DL", "1080p", "h264")
    assert "DD+" in c.audio and c.channels == "5.1" and c.group == "GRP"


@pytest.mark.parametrize("name,source", [
    ("Movie.2020.1080p.BluRay.x264-AAA.mkv", "BluRay"), ("Movie.2020.WEBRip.x265.mkv", "WEBRip"),
    ("Movie.2020.HDTV.720p.mkv", "HDTV"), ("Movie.2020.DVDRip.XviD.avi", "DVD"),
    ("Movie.2020.HDCAM.mkv", "CAM"), ("Movie.2020.BDMV.mkv", "ISO"), ("movie.iso", "ISO"),
    ("random name.mkv", None)])
def test_sources(name, source):
    assert parse_name(name).source == source


def test_hdr10plus_not_hdr10():
    assert parse_name("Film.2160p.WEB-DL.HDR10+.mkv").hdr == {"HDR10+"}


def test_resolution_tier_keeps_scope_films_in_their_class():
    assert resolution_tier(3840, 1600)[1] == "uhd"
    assert resolution_tier(1920, 800)[1] == "fhd"
    assert resolution_tier(1280, 536)[1] == "hd"


def test_bitrate_score_is_monotonic():
    scores = [bitrate_score(x / 100) for x in range(0, 40)]
    assert scores == sorted(scores) and scores[0] == 5 and scores[-1] == 100


def test_hdr_classification():
    assert classify_hdr(video(dv=(7, 6)), {})[0] == "DV P7"
    assert classify_hdr(video(dv=(8, 1)), {})[0] == "DV P8.1"
    assert classify_hdr(video(dv=(5, 0)), {})[0] == "DV P5"
    assert classify_hdr(video(), {})[0] == "HDR10"
    assert classify_hdr(video(transfer="arib-std-b67"), {})[0] == "HLG"
    assert classify_hdr(video(transfer="bt709"), {})[0] == "SDR"
    frame = {"side_data_list": [{"side_data_type": "HDR Dynamic Metadata SMPTE2094-40 (HDR10+)"}]}
    assert classify_hdr(video(), frame) == ("HDR10+", True)


def test_audio_labels():
    assert audio_label(audio("truehd", 8, "Dolby TrueHD + Dolby Atmos"))[0] == "TrueHD Atmos"
    assert audio_label(audio("dts", 8, "DTS-HD MA + DTS:X"))[0] == "DTS:X"
    assert audio_label(audio("dts", 6, "DTS-HD MA")) == ("DTS-HD MA", True)
    assert audio_label(audio("dts", 6, "DTS"))[0] == "DTS"
    assert audio_label(audio("eac3", 6, "Dolby Digital Plus + Dolby Atmos"))[0] == "DD+ Atmos"
    assert audio_label(audio("pcm_s24le", 2))[0] == "LPCM"


def test_remux_beats_web_and_is_explained():
    cmp = compare(evaluate(uhd_remux()), evaluate(web_1080()), PROFILES["Équilibré"])
    assert cmp.winner == "A" and cmp.total_a > 90 and cmp.total_b < 70
    assert "Le fichier A est de meilleure qualité" in verdict(cmp)
    assert any(line.startswith("A gagne") for line in explanations(cmp))


def test_swapping_files_flips_the_winner():
    cmp = compare(evaluate(web_1080()), evaluate(uhd_remux()))
    assert cmp.winner == "B"


def test_equal_files_are_a_tie():
    cmp = compare(evaluate(web_1080()), evaluate(web_1080()))
    assert cmp.winner == "égalité" and abs(cmp.total_a - cmp.total_b) < 1e-9


def test_weights_change_the_result():
    sdr = PROFILES["Écran SDR"]
    hdr_heavy = {**PROFILES["Équilibré"], "hdr": 60}
    a, b = evaluate(uhd_remux()), evaluate(web_1080())
    assert compare(a, b, hdr_heavy).total_a - compare(a, b, hdr_heavy).total_b > \
        compare(a, b, sdr).total_a - compare(a, b, sdr).total_b


def test_fake_remux_is_corrected_and_flagged():
    fake = make(REMUX, [video(bit_rate=9_000_000, dv=(8, 1)), audio("eac3", 6, bit_rate=640_000)], size_gb=9)
    ev = evaluate(fake)
    assert ev.source.label != "Remux"
    assert any(w.level == "alert" and "remux" in w.text.lower() for w in ev.warnings)
    assert any("Atmos" in w.text or "TrueHD" in w.text for w in ev.warnings)


def test_remux_label_on_720p_is_corrected():
    fake = make("Film.2160p.REMUX.mkv",
                [video(1280, 720, "h264", bit_rate=1_500_000, transfer="bt709", pix="yuv420p"), audio("aac", 2)])
    ev = evaluate(fake)
    assert ev.source.label != "Remux" and ev.cats["bitrate"].score < 90


def test_fake_4k_and_missing_hdr_are_flagged():
    fake = make("Film.2160p.WEB-DL.DV.HDR10.mkv",
                [video(1920, 1080, "h264", bit_rate=5_000_000, transfer="bt709", pix="yuv420p"),
                 audio("aac", 2)])
    texts = " ".join(w.text for w in evaluate(fake).warnings)
    assert "annonce 2160p" in texts and "Dolby Vision" in texts and "HDR" in texts


def test_lossy_audio_below_reference_bitrate_scores_lower():
    hi = evaluate(make("a.mkv", [video(), audio("ac3", 6, bit_rate=640_000)]))
    lo = evaluate(make("a.mkv", [video(), audio("ac3", 6, bit_rate=192_000)]))
    assert hi.cats["audio"].score > lo.cats["audio"].score


def test_name_without_source_is_inferred_from_bitrate():
    ev = evaluate(make("sans titre.mkv", [video(bit_rate=60_000_000, dv=(7, 6)), audio("truehd", 8)]))
    assert ev.source.label == "Remux" and ev.source.origin == "déduit du débit"
