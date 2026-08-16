@echo off
TITLE OmniScribe - Installer
REM No elevation needed (audit backlog): shortcuts are per-user, uv
REM installs into the user profile, and nothing writes to machine
REM locations. The old admin self-elevation block forced an
REM unnecessary UAC prompt.

echo Starting installation...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
