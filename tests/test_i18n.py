import json
import re
from pathlib import Path

import pytest

from vidcompare import i18n
from vidcompare.i18n import CODES, LANGUAGES

LOC = Path(i18n.__file__).parent / "locales"
PH = re.compile(r"\{(\w+)\}")


def _load(code):
    return json.loads((LOC / f"{code}.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _reset():
    i18n.set_language("fr")
    yield
    i18n.set_language("fr")


def test_ten_languages_declared():
    assert len(LANGUAGES) == 10 and len(set(CODES)) == 10


@pytest.mark.parametrize("code", CODES)
def test_catalog_complete_and_placeholders_match(code):
    fr, und = _load("fr"), _load("und")
    tr = _load(code)
    missing = [k for k in fr if k not in tr and k not in und]
    assert not missing, missing[:10]
    assert not [k for k in tr if k not in fr]
    for k, v in tr.items():
        assert sorted(PH.findall(v)) == sorted(PH.findall(fr[k])), k


@pytest.mark.parametrize("code", CODES)
def test_every_language_is_offered(code):
    assert i18n.coverage(code) >= i18n.MIN_COVERAGE
    assert code in dict(i18n.available())


def test_fallback_and_unknown_key():
    i18n.set_language("es")
    assert i18n.t("no.such.key") == "no.such.key"
    assert i18n.t("device.dv") == "Dolby Vision"


def test_unknown_language_keeps_current():
    i18n.set_language("en")
    assert i18n.set_language("xx") == "en"


def test_rtl_and_decimal():
    assert i18n.is_rtl("ar") and not i18n.is_rtl("fr")
    assert i18n.decimal_sep("fr") == "," and i18n.decimal_sep("en") == "."


def test_csv_keys_are_ascii_identifiers():
    for code in CODES:
        for k, v in _load(code).items():
            if k.startswith("csv.") and k not in ("csv.film", "csv.series", "csv.yes", "csv.no", "csv.tie"):
                assert re.fullmatch(r"[a-z0-9_]+", v) or v == "HDR", (code, k, v)


def test_code_keys_exist():
    import ast
    used = set()
    for p in Path(i18n.__file__).parent.glob("*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("t", "tr")
                    and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                used.add(n.args[0].value)
    have = set(_load("fr")) | set(_load("und"))
    assert not [k for k in used if k not in have and not k.endswith(".")]
