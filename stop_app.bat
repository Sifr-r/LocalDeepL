@echo off
title Stopping OmniScribe
echo Stopping Background OCR Services...

powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'src.omniscribe.server:app' -or $_.CommandLine -match 'celery -A src.omniscribe.api.celery_app' } | Invoke-CimMethod -MethodName Terminate | Out-Null"

echo.
echo All OCR background services have been stopped.
timeout /t 3
