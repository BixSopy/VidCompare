**English** · [Français](README.fr.md)

# VidCompare

Compare the quality of two video files, torrents, magnet links or pasted MediaInfo reports. VidCompare gives each a score out of 100 and says which one is better, and why.

Everything runs on your PC. No file is uploaded. The only network request is an optional daily check for a newer version, which you can turn off ([privacy](PRIVACY.md)).

## What it looks at

Source (Remux, BluRay, WEB-DL...), resolution, video bitrate and codec, HDR (HDR10, HDR10+, Dolby Vision), audio format and channels (TrueHD Atmos, DTS-HD MA...), and what your hardware can actually play. It also flags suspicious files: a "Remux" with a low bitrate, a "4K" that is upscaled, a missing audio track.

- **Compare**: two files side by side, with a verdict, a criterion-by-criterion breakdown, and optional frame comparison and VMAF measurement.
- **Library**: rank many files, find which movies or seasons would gain the most from a better version. VidCompare says what to look for, not where to find it.
- **Settings**: weighting profiles, your TV and sound system, preferred track language, group reputation, theme (Cinema or pure-black OLED).
- **10 languages**: English, 中文, हिन्दी, Español, العربية, Français, বাংলা, Português, Русский, Bahasa Indonesia. The default follows Windows.
- **Command line**: `VidCompare` or `python -m vidcompare.cli A.mkv B.mkv --lang en`.

Torrent files and magnet links are only *read* for their names and sizes, to estimate quality. VidCompare does not search for, download or share anything, and will not.

## Install (Windows 10/11, 64-bit)

1. Download `VidCompare-Setup.exe` from the [Releases](../../releases) page, or the portable `VidCompare-win64.zip`.
2. The installer can install FFmpeg and WebView2 for you through `winget`. By hand:

   ```
   winget install Gyan.FFmpeg
   winget install Microsoft.EdgeWebView2Runtime
   ```

   FFmpeg is required to read videos. Choose a "full" build if you want the VMAF measurement. You can also point to `ffprobe.exe` in Settings.
3. The app is not code-signed yet, so Windows SmartScreen may warn on first launch ("More info" > "Run anyway"). The code is open: you can build it yourself.

## Run from source

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run_app.py
```

Build the executable and installer: `powershell -File tools/build.ps1` (needs PyInstaller; the installer needs Inno Setup 6).

## Honest limits

- Scores are **estimates** based on file metadata and public technical documentation, not a perceptual measurement. VMAF (optional) is closer to what you see, but is unreliable on HDR.
- Torrent and magnet scores are guesses from the name and size.
- **Translations are machine-made.** Native speakers, please [fix them](CONTRIBUTING.md#translations).
- Windows only for now.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). Third-party components: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
