# Third-party notices

VidCompare is MIT-licensed. It uses the components below. Their own licenses apply to them, not to VidCompare.

| Component | Role | License | Shipped in the installer? |
|---|---|---|---|
| [FFmpeg / ffprobe](https://ffmpeg.org) | reads video files, extracts frames, computes VMAF | LGPL 2.1+ or GPL 2+, depending on the build | **No.** Installed separately by the user (see README). VidCompare runs it as an external program and does not link to it. |
| [pywebview](https://github.com/r0x0r/pywebview) | native window around the web UI | BSD-3-Clause | Yes |
| [pythonnet](https://github.com/pythonnet/pythonnet) | .NET bridge used by pywebview on Windows | MIT | Yes |
| [clr_loader](https://github.com/pythonnet/clr-loader) | .NET runtime loader | MIT | Yes |
| proxy_tools, bottle, typing_extensions | pywebview dependencies | MIT / PSF | Yes |
| [Python](https://www.python.org) | runtime | PSF License | Yes |
| [PyInstaller](https://pyinstaller.org) | packaging (build tool only) | GPL-2.0 with bootloader exception: the built app may use any license | Bootloader only |
| [Microsoft Edge WebView2](https://developer.microsoft.com/microsoft-edge/webview2/) | rendering engine of the window | Microsoft Software License Terms | **No.** Preinstalled on Windows 11; the installer downloads Microsoft's bootstrapper if missing. |

VMAF is a metric by Netflix ([BSD-2-Clause-Patent](https://github.com/Netflix/vmaf)), computed by FFmpeg's `libvmaf` filter.

The device and quality tables in `vidcompare/scoring.py` are the author's own estimates, drawn from public technical documentation. They are not endorsed by any brand named in the app. Dolby, Dolby Vision, Atmos, DTS, HDR10+, HEVC and other names are trademarks of their respective owners and are used only to describe file formats.
