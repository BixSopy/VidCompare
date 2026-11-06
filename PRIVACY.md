# Privacy

VidCompare runs entirely on your computer.

- It **does not send any personal data**: no telemetry, no account, no tracking.
- The only network request is the **update check**: once a day at launch (and when you click "Check now"), VidCompare asks `api.github.com` for the latest release number. GitHub sees your IP address and the program name and version, like any web request. You can turn it off in Settings > Updates, and then VidCompare makes no network request at all.
- Files you select are read locally, through FFmpeg/ffprobe. They are never uploaded.
- Settings, history, the analysis cache and the error log are stored in `%APPDATA%\VidCompare` on your PC. Delete that folder to erase them. The history can also be cleared in the app.
- The error log (`vidcompare.log`) can contain file names and paths. Review it before sharing it in a bug report.
