@echo off
title Stopping OmniScribe
echo Stopping OmniScribe background services...

REM Match the installed-package entry points start_app.vbs launches
REM (uvicorn omniscribe.server:app, celery -A omniscribe.api.tasks)
REM plus the legacy src.* namespace forms so older sessions die too.
powershell -NoProfile -Command "$pats = 'omniscribe.server:app', 'celery -A omniscribe.api.tasks', 'src.omniscribe.server:app', 'celery -A src.omniscribe.api.celery_app'; Get-CimInstance Win32_Process | Where-Object { $cl = $_.CommandLine; $pats | Where-Object { $cl -like ('*' + $_ + '*') } } | ForEach-Object { Write-Host ('Stopping PID ' + $_.ProcessId + ' (' + $_.Name + ')'); $_ | Invoke-CimMethod -MethodName Terminate | Out-Null }"

REM Stop the redis broker container start_app.vbs created. Guarded so
REM machines without Docker simply skip the step (audit backlog: the
REM redis-local-ocr container used to keep running after stop).
where docker >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    REM for /f runs zero iterations when the container is absent —
    REM avoids the parse-time %%ERRORLEVEL%% expansion trap of
    REM nested if blocks.
    for /f %%i in ('docker ps -q --filter "name=redis-local-ocr"') do (
        echo Stopping redis-local-ocr container...
        docker stop redis-local-ocr >nul
    )
)

echo.
echo All OmniScribe background services have been stopped.
timeout /t 3
