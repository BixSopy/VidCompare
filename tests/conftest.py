import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


import pytest


@pytest.fixture(autouse=True)
def _french_by_default(monkeypatch):
    """Les tests vérifient des textes français : on fixe la langue, quelle que soit celle de la machine."""
    from vidcompare import i18n
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "fr")
    i18n.set_language("fr")
