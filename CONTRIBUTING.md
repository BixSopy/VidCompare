# Contributing

Bug reports, translations and code are welcome.

## Set up

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest
```

Run the UI in a browser while developing: `python -m vidcompare.webapp --dev`, then open http://127.0.0.1:5174/.
Install FFmpeg (`winget install Gyan.FFmpeg`) to run the integration tests. They are skipped without it.

## Translations

Texts live in `vidcompare/locales/<code>.json` (`fr.json` is the reference). Existing translations are machine-made, so **corrections from native speakers are the most useful contribution.**

1. Edit `vidcompare/locales/<code>.json`. Keep every `{placeholder}` unchanged.
2. Run `python tools/check_locale.py <code>`. It must print `OK`.
3. Open a pull request. To add a language, also add it to `LANGUAGES` in `vidcompare/i18n.py` and to `vidcompare/langs.py`.

## Pull requests

- One topic per PR. Add or update tests. `pytest` must pass.
- No code that searches for, downloads or shares copyrighted files.
- Scoring changes (weights, tables) need a short justification with a source.
