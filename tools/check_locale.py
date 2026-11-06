"""Vérifie un catalogue : clés manquantes/inconnues et paramètres {x} identiques au français.
Usage : python tools/check_locale.py <code>"""
import json, re, sys
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "vidcompare" / "locales"
PH = re.compile(r"\{(\w+)\}")


def check(code: str) -> list[str]:
    fr = json.loads((D / "fr.json").read_text(encoding="utf-8"))
    und = json.loads((D / "und.json").read_text(encoding="utf-8"))
    tr = json.loads((D / f"{code}.json").read_text(encoding="utf-8"))
    errs = [f"manquante: {k}" for k in fr if k not in tr and k not in und]
    errs += [f"inconnue: {k}" for k in tr if k not in fr]
    for k, v in tr.items():
        if k in fr and sorted(PH.findall(v)) != sorted(PH.findall(fr[k])):
            errs.append(f"paramètres différents: {k}")
    return errs


if __name__ == "__main__":
    e = check(sys.argv[1])
    print("\n".join(e) or "OK")
    sys.exit(1 if e else 0)
