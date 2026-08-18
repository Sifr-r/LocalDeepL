# F5-15 audit fix: derive the target path from this script's
# location instead of hardcoding ``D:\OmniScribe\start_app.vbs``.
# The previous absolute path only worked on the audit author's
# host and silently scanned the wrong file (or nothing) for any
# other developer. ``Split-Path -Parent $MyInvocation.MyCommand.Path``
# gives the directory this script lives in, which is the repo
# root in this layout; combined with ``Join-Path`` we get the
# same ``start_app.vbs`` path without a hardcoded drive letter.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$path = Join-Path -Path $scriptDir -ChildPath 'start_app.vbs'
if (-not (Test-Path -Path $path -PathType Leaf)) {
    Write-Host "::error::$path not found; cannot run EOL check."
    exit 1
}
$bytes = [System.IO.File]::ReadAllBytes($path)
$crlf = 0
$lfOnly = 0
for ($i = 0; $i -lt $bytes.Length; $i++) {
    if ($bytes[$i] -eq 13 -and ($i + 1) -lt $bytes.Length -and $bytes[$i + 1] -eq 10) {
        $crlf++
        $i++
    }
    elseif ($bytes[$i] -eq 10) {
        $lfOnly++
    }
}
Write-Host ("CRLF: " + $crlf + "  LF-only: " + $lfOnly + "  size: " + $bytes.Length)
