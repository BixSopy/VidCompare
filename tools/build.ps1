# Builds build_out\VidCompare-win64.zip (portable) and, if Inno Setup is installed, build_out\VidCompare-Setup.exe.
# FFmpeg is NOT bundled (see THIRD_PARTY_NOTICES.md).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$out = Join-Path $root "build_out"
$tmp = Join-Path $root "build_tmp"
Remove-Item $out, $tmp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $out, $tmp | Out-Null

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $py -m PyInstaller --noconfirm --windowed --name VidCompare `
    --distpath "$out\dist" --workpath "$tmp\work" --specpath $tmp --paths $root `
    --add-data "$root\ui;ui" --add-data "$root\vidcompare\locales;vidcompare\locales" `
    --collect-all webview --collect-all pythonnet --collect-all clr_loader `
    --exclude-module PySide6 --exclude-module shiboken6 "$root\run_app.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Copy-Item LICENSE, THIRD_PARTY_NOTICES.md, PRIVACY.md "$out\dist\VidCompare\"
Compress-Archive -Path "$out\dist\VidCompare\*" -DestinationPath "$out\VidCompare-win64.zip"

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    $ver = (& $py -c "import vidcompare; print(vidcompare.__version__)")
    & $iscc "/DAppVersion=$ver" "/DSourceDir=$out\dist\VidCompare" "/DOutDir=$out" "$root\tools\installer.iss"
} else {
    Write-Warning "Inno Setup not found: installer skipped (zip only)."
}
