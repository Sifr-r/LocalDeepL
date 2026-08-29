$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "======================================================="
Write-Host "Installing OmniScribe Dependencies"
Write-Host "======================================================="

# 1. Check/Install uv
#
# Audit backlog hardening: the old one-liner downloaded a remote
# script and executed it sight-unseen. Prefer winget (package manifest
# + signature verification); the fallback downloads the official
# installer to a temp file, sanity-checks it, and runs it from disk
# so remote code never executes directly from the network stream.
if (!(Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found. Installing uv..."
    $installed = $false
    if (Get-Command "winget" -ErrorAction SilentlyContinue) {
        Write-Host "Installing uv via winget..."
        winget install --id astral-sh.uv -e --silent --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -eq 0) { $installed = $true }
        else { Write-Host "winget install failed (exit $LASTEXITCODE); falling back to the astral.sh installer." -ForegroundColor Yellow }
    }
    if (!$installed) {
        $uvInstaller = Join-Path -Path $env:TEMP -ChildPath "uv-install.ps1"
        $uvInstallerSha = Join-Path -Path $env:TEMP -ChildPath "uv-install.ps1.sha256"
        try {
            # Audit P2-15: pin the uv installer to the same version
            # the Dockerfile uses (UV_VERSION=0.11.16), so the fallback
            # path here matches the canonical supply-chain pin and a
            # silently-republished latest can't surprise this script.
            # Bump the Dockerfile in lockstep when bumping this.
            #
            # F5-29 audit fix: verify installer integrity before
            # executing. If a SHA-256 sidecar is published alongside
            # the script, verify the hash matches; validate that the
            # payload is non-empty and well-formed before passing to
            # powershell. The installer script itself internally verifies
            # SHA-256 hashes of downloaded uv release binaries.
            $uvVersion = "0.11.16"
            Invoke-RestMethod -Uri "https://astral.sh/uv/${uvVersion}/install.ps1" -OutFile $uvInstaller
            $sidecarDownloaded = $false
            try {
                Invoke-RestMethod -Uri "https://astral.sh/uv/${uvVersion}/install.ps1.sha256" -OutFile $uvInstallerSha
                $sidecarDownloaded = $true
            } catch {
                # Upstream astral.sh does not host .sha256 sidecars for script wrappers;
                # the installer script validates binary SHA256 directly on download.
            }
            if ($sidecarDownloaded -and (Test-Path $uvInstallerSha)) {
                $expectedHash = (Get-Content -Path $uvInstallerSha -Raw -ErrorAction SilentlyContinue).Trim().Split(' ')[0]
                if (![string]::IsNullOrWhiteSpace($expectedHash)) {
                    $actualHash = (Get-FileHash -Path $uvInstaller -Algorithm SHA256).Hash.ToLower()
                    if ($actualHash -ne $expectedHash.ToLower()) {
                        throw "uv installer SHA-256 mismatch: expected $expectedHash, got $actualHash."
                    }
                }
            }
            # Sanity check: a truncated/empty or non-script payload must
            # never reach the interpreter.
            $content = Get-Content -Path $uvInstaller -Raw -ErrorAction SilentlyContinue
            if ([string]::IsNullOrWhiteSpace($content) -or $content.Length -lt 1000) {
                throw "Downloaded uv installer is empty or truncated."
            }
            & powershell -NoProfile -ExecutionPolicy Bypass -File $uvInstaller
            if ($LASTEXITCODE -ne 0) { throw "uv installer script exited with $LASTEXITCODE." }
        } catch {
            Write-Host "ERROR: Failed to install uv. Please install it manually from https://docs.astral.sh/uv/" -ForegroundColor Red
            Write-Host "Underlying error: $_" -ForegroundColor Red
            exit 1
        } finally {
            Remove-Item -Path $uvInstaller -ErrorAction SilentlyContinue
            Remove-Item -Path $uvInstallerSha -ErrorAction SilentlyContinue
        }
    }
    # Refresh PATH so the just-installed uv is visible to the rest of this script.
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User") + ";$env:LOCALAPPDATA\Microsoft\WinGet\Links"
    if (!(Get-Command "uv" -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: uv still not on PATH after installation. Try restarting the installer." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "uv is already installed."
}

# 2. Sync dependencies
Write-Host "`nSyncing python dependencies with uv..."
Set-Location -Path $ScriptDir
uv sync --extra web --extra preprocessing --extra async-translation --extra lexicon
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: uv sync failed. See the output above for details." -ForegroundColor Red
    exit 1
}

# 2b. Verify the install actually completed (a venv exists and python runs).
Write-Host "`nVerifying the install..."
& uv run python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: uv run python --version failed after sync. The virtual environment may be broken." -ForegroundColor Red
    exit 1
}
Write-Host "Python environment OK."

# 3. Check Docker
Write-Host "`nChecking for Docker (required for Redis)..."
if (!(Get-Command "docker" -ErrorAction SilentlyContinue)) {
    Write-Host "WARNING: Docker is not installed or not in PATH." -ForegroundColor Yellow
    Write-Host "Docker is required to run Redis for the translation features." -ForegroundColor Yellow
    Write-Host "Please install Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
} else {
    Write-Host "Docker is installed."
}

# 4. Create Shortcuts
Write-Host "`nCreating shortcuts..."

$WshShell = New-Object -comObject WScript.Shell

# Desktop Shortcut
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path -Path $DesktopPath -ChildPath "OmniScribe.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = Join-Path -Path $ScriptDir -ChildPath "start_app.vbs"
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.IconLocation = "%SystemRoot%\system32\SHELL32.dll,22"
$Shortcut.Save()
Write-Host "Created Desktop Shortcut: $ShortcutPath"

# Start Menu Shortcut
$StartMenuPath = [Environment]::GetFolderPath("Programs")
$ShortcutPathSM = Join-Path -Path $StartMenuPath -ChildPath "OmniScribe.lnk"
$ShortcutSM = $WshShell.CreateShortcut($ShortcutPathSM)
$ShortcutSM.TargetPath = Join-Path -Path $ScriptDir -ChildPath "start_app.vbs"
$ShortcutSM.WorkingDirectory = $ScriptDir
$ShortcutSM.IconLocation = "%SystemRoot%\system32\SHELL32.dll,22"
$ShortcutSM.Save()
Write-Host "Created Start Menu Shortcut: $ShortcutPathSM"

# Clean up legacy Stop Shortcut if present
$LegacyStopShortcutSM = Join-Path -Path $StartMenuPath -ChildPath "Stop OmniScribe.lnk"
if (Test-Path $LegacyStopShortcutSM) {
    Remove-Item -Force $LegacyStopShortcutSM
}

Write-Host "`n======================================================="
Write-Host "Installation Complete!"
Write-Host "======================================================="
Write-Host ""
Write-Host "IMPORTANT: If this is your first install, log out of Windows and back in" -ForegroundColor Cyan
Write-Host "before using the Desktop / Start Menu shortcut. The uv installer adds" -ForegroundColor Cyan
Write-Host "uv to your user PATH, and that update only takes effect for new logon sessions." -ForegroundColor Cyan
Write-Host ""
Write-Host "After logging back in, double-click the OmniScribe shortcut on your Desktop to start the app." -ForegroundColor Cyan
Write-Host "If something does not come up, check start_app.log next to this installer." -ForegroundColor Cyan
Write-Host ""

# Audit P2-XX / Sprint 5 follow-up: Microsoft Defender on a small
# fraction of Windows hosts flags Apache Arrow's
# ``arrow_substrait.dll`` (pulled in transitively by the optional
# ``[lexicon]`` extra via lancedb) as ``Trojan:Win32/Wacatac.B!ml``.
# This is a known false positive (same DLL ships in the official
# Arrow PyPI wheel; signature verifies against the Arrow maintainers'
# cert). We offer an opt-in Defender exclusion scoped to the venv
# site-packages directory so the exclusion does NOT cover the rest of
# the host. See ``SECURITY.md`` §"Platform Notes" for the rationale.
$venvSitePackages = Join-Path -Path (Join-Path -Path $ScriptDir -ChildPath ".venv") -ChildPath "Lib\site-packages"
if (Test-Path $venvSitePackages) {
    $addExclusion = Read-Host "Add a Microsoft Defender exclusion for $venvSitePackages (arrow_substrait.dll false positive)? [y/N]"
    if ($addExclusion -match "^[Yy]$") {
        try {
            Add-MpPreference -ExclusionPath $venvSitePackages -ErrorAction Stop
            Write-Host "Added Defender exclusion for $venvSitePackages." -ForegroundColor Green
        } catch {
            Write-Host "Could not add Defender exclusion: $_" -ForegroundColor Yellow
            Write-Host "  (Run this script as Administrator, or add the path manually.)" -ForegroundColor Yellow
        }
    }
}
