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
        try {
            Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" -OutFile $uvInstaller
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
# uv will automatically download the correct python version based on .python-version if it is missing
uv sync --extra web --extra preprocessing
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: uv sync failed. See the output above for details." -ForegroundColor Red
    exit 1
}

# 2a. Build frontend static assets (if npm is available)
#
# `npm ci` installs exactly what package-lock.json pins (reproducible,
# and picks up security updates the way Dependabot intends). Every
# npm step is exit-code checked: a silent frontend build failure
# used to leave the installer reporting success with stale assets
# (audit backlog).
if (Get-Command "npm" -ErrorAction SilentlyContinue) {
    Write-Host "`nBuilding Svelte 5 + Tailwind v4 frontend..."
    Set-Location -Path (Join-Path -Path $ScriptDir -ChildPath "frontend")
    npm ci
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: npm ci failed. See the output above for details." -ForegroundColor Red
        exit 1
    }
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: npm run build failed. See the output above for details." -ForegroundColor Red
        exit 1
    }
    Set-Location -Path $ScriptDir
} else {
    Write-Host "`nNote: npm not found in PATH; skipping frontend build (pre-built static assets will be used)." -ForegroundColor Yellow
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

# Stop Shortcut (Start Menu)
$StopShortcutPathSM = Join-Path -Path $StartMenuPath -ChildPath "Stop OmniScribe.lnk"
$StopShortcutSM = $WshShell.CreateShortcut($StopShortcutPathSM)
$StopShortcutSM.TargetPath = Join-Path -Path $ScriptDir -ChildPath "stop_app.bat"
$StopShortcutSM.WorkingDirectory = $ScriptDir
$StopShortcutSM.IconLocation = "%SystemRoot%\system32\SHELL32.dll,28" # Stop icon
$StopShortcutSM.Save()
Write-Host "Created Stop Shortcut in Start Menu: $StopShortcutPathSM"

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
