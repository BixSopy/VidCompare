import io
import json

from vidcompare import updates
from vidcompare.cache import Cache
from vidcompare.history import History
from vidcompare.webapp import Api, Store

REAL_FETCH = updates.fetch_latest      # la version réelle, avant le blocage réseau de conftest


def make_api(tmp_path):
    return Api(Store(tmp_path / "s.json"), History(tmp_path / "h.json"), Cache(tmp_path / "c.json"))


def test_version_comparison():
    assert updates.is_newer("6.0.1", "6.0.0") and updates.is_newer("v7", "6.9.9")
    assert not updates.is_newer("6.0.0", "6.0.0") and not updates.is_newer("5.9", "6.0.0")
    assert not updates.is_newer("n'importe quoi", "6.0.0")


def test_fetch_latest_parses_and_rejects_foreign_urls(monkeypatch):
    def fake(payload):
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return lambda req, timeout=5: R(json.dumps(payload).encode())
    monkeypatch.setattr(updates.urllib.request, "urlopen",
                        fake({"tag_name": "v6.1.0", "html_url": updates.RELEASE_PREFIX + "releases/tag/v6.1.0"}))
    assert REAL_FETCH("6.0.0") == {"version": "6.1.0", "url": updates.RELEASE_PREFIX + "releases/tag/v6.1.0"}
    monkeypatch.setattr(updates.urllib.request, "urlopen",
                        fake({"tag_name": "v9.0.0", "html_url": "https://evil.example/x"}))
    assert REAL_FETCH("6.0.0") is None


def test_manual_check_reports_available_version(tmp_path, monkeypatch):
    api = make_api(tmp_path)
    monkeypatch.setattr(updates, "fetch_latest", lambda c, timeout=5.0: {"version": "99.0.0", "url": updates.RELEASE_PREFIX + "x"})
    s = api.check_update()
    assert s["update"]["version"] == "99.0.0" and "99.0.0" in s["toast"]


def test_manual_check_failure_and_up_to_date(tmp_path, monkeypatch):
    api = make_api(tmp_path)
    assert api.check_update()["update"] is None            # réseau coupé : message d'échec, aucune exception
    from vidcompare import __version__
    monkeypatch.setattr(updates, "fetch_latest", lambda c, timeout=5.0: {"version": __version__, "url": updates.RELEASE_PREFIX + "x"})
    assert api.check_update()["update"] is None


def test_auto_check_can_be_disabled_and_persists(tmp_path):
    api = make_api(tmp_path)
    assert api.get_state()["updateCheck"] is True
    assert api.set_update_check(False)["updateCheck"] is False
    assert make_api(tmp_path).get_state()["updateCheck"] is False
