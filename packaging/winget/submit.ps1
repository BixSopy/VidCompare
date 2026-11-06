# Soumet les manifestes winget a microsoft/winget-pkgs (fork + branche + pull request), sans cloner le gros depot.
# Prerequis : gh connecte (gh auth status). Usage : powershell -File packaging\winget\submit.ps1
$ErrorActionPreference = "Stop"
$gh = "$env:ProgramFiles\GitHub CLI\gh.exe"
$me = (& $gh api user --jq .login)
$ver = "6.1.1"
$dir = "manifests/b/BixSopy/VidCompare/$ver"
$branch = "BixSopy.VidCompare-$ver"

& $gh repo fork microsoft/winget-pkgs --clone=false 2>$null
& $gh repo sync "$me/winget-pkgs" --branch master | Out-Null
$sha = (& $gh api "repos/$me/winget-pkgs/git/ref/heads/master" --jq .object.sha)
& $gh api -X POST "repos/$me/winget-pkgs/git/refs" -f "ref=refs/heads/$branch" -f "sha=$sha" | Out-Null

Get-ChildItem $PSScriptRoot -Filter "BixSopy.VidCompare*.yaml" | ForEach-Object {
    $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($_.FullName))
    & $gh api -X PUT "repos/$me/winget-pkgs/contents/$dir/$($_.Name)" `
        -f "message=New package: BixSopy.VidCompare version $ver" -f "content=$b64" -f "branch=$branch" | Out-Null
    Write-Host "ajoute $($_.Name)"
}

$body = @"
New package: **VidCompare** $ver, a free open-source (MIT) tool that compares the quality of two video files.

- Installer: Inno Setup, built by GitHub Actions from the public repository, attached to the GitHub release.
- Declares FFmpeg (Gyan.FFmpeg) and WebView2 as package dependencies.
- The installer is not code-signed yet (SmartScreen may warn).
- Source: https://github.com/BixSopy/VidCompare
"@
& $gh pr create --repo microsoft/winget-pkgs --head "$me`:$branch" --base master `
    --title "New package: BixSopy.VidCompare version $ver" --body $body
