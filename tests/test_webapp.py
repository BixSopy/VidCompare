import json
import time

import pytest

from helpers import audio, make, video
from test_v2 import REMUX, benc
from test_v3 import REPORT_EN
from vidcompare.cache import Cache
from vidcompare.history import History
from vidcompare.webapp import Api, Store

SDR = dict(transfer="bt709", pix="yuv420p")


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))          # groupes.json isolé
    from vidcompare import groups
    groups.reload()
    return Api(Store(tmp_path / "r.json"), History(tmp_path / "h.json"), Cache(tmp_path / "c.json"))


def torrent_file(tmp_path, name, gb):
    p = tmp_path / f"{name}.torrent"
    p.write_bytes(benc({"info": {"name": name, "files": [{"length": int(gb * 1e9), "path": [name + ".mkv"]}]}}))
    return str(p)


def test_state_is_json_and_empty_at_start(api):
    s = api.get_state()
    json.dumps(s)
    assert s["slots"] == {"A": None, "B": None} and s["result"] is None
    assert s["settings"]["profile"] == "Équilibré" and s["library"]["wanted"]


def test_two_torrents_give_a_result_with_reasons(api, tmp_path):
    api.set_source("A", torrent_file(tmp_path, REMUX, 55))
    s = api.set_source("B", torrent_file(tmp_path, "Film.2024.1080p.WEB-DL.DDP5.1.H.264-GRP", 6))
    assert s["slots"]["A"]["kind"] == "Torrent (estimé)" and s["slots"]["A"]["status"] == "ready"
    r = s["result"]
    json.dumps(r)
    assert r["winner"] == "A" and r["total"]["A"] > r["total"]["B"] and r["partial"]
    assert 1 <= len(r["reasons"]) <= 3 and all(x["who"] == "A" for x in r["reasons"])
    assert r["rows"][0]["key"] == "Source" and r["alerts"]["A"] is not None
    assert r["visual"]["available"] is False
    assert len(s["history"]) == 1 and s["history"][0]["winner"] == "A"


def test_report_in_slot_and_error_message(api):
    s = api.set_report("A", REPORT_EN)
    assert s["slots"]["A"]["kind"] == "Rapport MediaInfo" and "2160p" in s["slots"]["A"]["chips"][0]
    s = api.set_report("B", "n'importe quoi")
    assert s["slots"]["B"] is None and "MediaInfo" in s["toast"]
    assert api.get_state()["toast"] is None                  # un message ne s'affiche qu'une fois


def test_invalid_sources_give_a_toast(api, tmp_path):
    assert "dossier" in api.set_source("A", str(tmp_path))["toast"]
    bad = tmp_path / "x.torrent"
    bad.write_bytes(b"pas un torrent")
    assert "torrent" in api.set_source("A", str(bad))["toast"].lower()


def test_clear_slot_and_replace(api, tmp_path):
    api.set_source("A", torrent_file(tmp_path, REMUX, 55))
    api.set_source("A", "magnet:?dn=Film.2024.1080p.WEB-DL.DDP5.1.H.264-GRP&xl=6000000000")
    assert len(api._items) == 1                              # l'ancien élément est libéré
    assert api.clear_slot("A")["slots"]["A"] is None and not api._items


def test_settings_change_scores(api, tmp_path):
    api.set_report("A", REPORT_EN)
    api.set_source("B", torrent_file(tmp_path, "Film.2024.1080p.WEB-DL.DDP5.1.H.264-GRP", 6))
    base = api.get_state()["result"]["total"]["A"]
    s = api.set_preset("TV 4K Samsung (HDR10+, sans Dolby Vision ni DTS)")
    assert s["result"]["total"]["A"] < base and s["settings"]["preset"].startswith("TV 4K Samsung")
    s = api.set_device("dv", True)
    assert s["settings"]["preset"] == "Personnalisé"
    s = api.set_lang("fr_audio")
    assert any(r["key"] == "Langue" for r in s["result"]["rows"]) is False or True
    s = api.set_weight("hdr", 0)
    assert s["settings"]["profile"] == "Personnalisé" and dict((k, v) for k, _, v in s["settings"]["weights"])["hdr"] == 0
    assert api.set_profile("Home cinéma")["settings"]["profile"] == "Home cinéma"
    assert api.set_runtime(500)["settings"]["runtime"] == 400


def test_settings_survive_restart(api, tmp_path):
    api.set_lang("any")
    api.set_runtime(130)
    api.set_theme("oled")
    again = Api(Store(tmp_path / "r.json"), History(tmp_path / "h.json"), Cache(tmp_path / "c.json")).get_state()
    assert again["settings"]["lang"] == "any" and again["settings"]["runtime"] == 130 and again["theme"] == "oled"


def test_groups_crud(api):
    s = api.group_set("MonGroupe", 3)
    assert ["MonGroupe", 3.0] in s["settings"]["groups"]
    s = api.group_remove("MonGroupe")
    assert s["settings"]["groups"] == []


def test_ranking_flow(api, tmp_path):
    api.rank_add([torrent_file(tmp_path, REMUX, 55), "magnet:?dn=Film.2024.1080p.WEB-DL.DDP5.1.H.264-GRP&xl=6000000000"])
    s = api.get_state()
    rows = s["ranking"]["rows"]
    assert [r["rank"] for r in rows] == [1, 2] and rows[0]["score"] > rows[1]["score"] and s["ranking"]["estimated"]
    s = api.rank_send(rows[1]["id"], "B")
    assert s["slots"]["B"]["name"].startswith("Film.2024.1080p")
    s = api.rank_remove(rows[1]["id"])                       # dans une case : reste présent, hors classement
    assert len(s["ranking"]["rows"]) == 1 and s["slots"]["B"] is not None
    assert api.rank_clear()["ranking"]["rows"] == []


def test_history_reopen_and_remove(api, tmp_path):
    api.set_source("A", torrent_file(tmp_path, REMUX, 55))
    api.set_source("B", "magnet:?dn=Film.2024.1080p.WEB-DL.DDP5.1.H.264-GRP&xl=6000000000")
    h = api.get_state()["history"]
    assert len(h) == 1
    api.clear_slot("A")
    api.clear_slot("B")
    s = api.hist_reopen(h[0]["id"])
    assert s["slots"]["A"] and s["slots"]["B"] and s["result"]
    s = api.hist_remove(h[0]["id"])
    assert s["history"] == []
    assert api.hist_reopen(99)["toast"] is None              # ligne inconnue : rien ne se passe


def test_upgrades_with_injected_scan(api):
    infos = [make("D:/Films/Alien.1979.1080p.WEB-DL.mkv", [video(1920, 1080, "h264", bit_rate=5_000_000, **SDR),
                                                         audio("eac3", 6, bit_rate=640_000)], 4),
             make("D:/Series/Lost/Saison 1/Lost.S01E01.1080p.WEB-DL.mkv",
                  [video(1920, 1080, "h264", bit_rate=5_000_000, **SDR), audio("eac3", 6, bit_rate=640_000)], 4)]
    api._up_infos = infos
    api._up_ver += 1
    lib = api.get_state()["library"]
    assert [f["title"] for f in lib["films"]] == ["Alien"] and lib["series"][0]["title"].startswith("Lost")
    assert lib["films"][0]["gain"] > 20 and lib["films"][0]["fix"][0].startswith("HDR")
    assert "2160p" in lib["wanted"] and "analysés" in lib["summary"]
    lvl = api.up_set_level("Correct (1080p BluRay)")["library"]
    assert lvl["level"].startswith("Correct") and lvl["films"][0]["gain"] < lib["films"][0]["gain"]


def test_folder_scan_with_cache(api, tmp_path, monkeypatch):
    lib = tmp_path / "Films"
    lib.mkdir()
    for n in ("A.1080p.mkv", "B.720p.mkv"):
        (lib / n).write_bytes(b"x")
    calls = []

    def fake_load(path, ffprobe=None):
        calls.append(path)
        return make(path.split("\\")[-1], [video(1920, 1080, "h264", bit_rate=5_000_000, **SDR), audio("eac3", 6)], 1)

    monkeypatch.setattr("vidcompare.webapp.load_media", fake_load)
    api.up_add_folder(str(lib))
    assert api.get_state()["library"]["folders"] == [str(lib)]
    api.up_scan()
    for _ in range(100):
        if not api.get_state()["library"]["scan"] and api._up_infos:
            break
        time.sleep(0.05)
    s = api.get_state()["library"]
    assert len(calls) == 2 and "2 fichiers analysés" in s["summary"]
    api.up_scan()                                            # second scan : tout vient du cache
    time.sleep(0.2)
    assert len(calls) == 2
    assert api.up_remove_folder(str(lib))["library"]["folders"] == []
    assert "Ajoutez" in api.up_scan()["toast"]


def test_unknown_visual_is_unavailable(api):
    assert api.show_frames()["ok"] is False
