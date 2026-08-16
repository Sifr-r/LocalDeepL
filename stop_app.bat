@echo off
title Stopping OmniScribe
echo Stopping OmniScribe background services...

REM M4 audit: graceful-then-hard kill. The previous CimMethod Terminate
REM call killed uvicorn/Celery mid-request, dropping in-flight OCR jobs.
REM Phase 1: taskkill /PID <pid> (graceful close request, no /F). Phase 2:
REM only if any process is still alive after the grace period, fall back to
REM the original CimMethod Terminate hard kill.

REM Phase 1: graceful close. Match the same installed-package entry points
REM start_app.vbs launches (uvicorn omniscribe.server:app, celery -A
REM omniscribe.api.tasks) plus the legacy src.* namespace forms so older
REM sessions die too. Grace period = 10s, polled at 1s.
powershell -NoProfile -Command "$pats = 'omniscribe.server:app', 'celery -A omniscribe.api.tasks', 'src.omniscribe.server:app', 'celery -A src.omniscribe.api.celery_app'; $GraceSec = 10; $procs = @(Get-CimInstance Win32_Process | Where-Object { $cl = $_.CommandLine; $pats | Where-Object { $cl -like ('*' + $_ + '*') } }); if ($procs.Count -eq 0) { Write-Host 'No matching OmniScribe processes found.' } else { Write-Host ('Found ' + $procs.Count + ' matching process(es); sending graceful shutdown (grace=' + $GraceSec + 's)'); $procs | ForEach-Object { Write-Host ('  taskkill /PID ' + $_.ProcessId + ' (' + $_.Name + ')'); & taskkill.exe /PID $_.ProcessId *> $null }; $deadline = (Get-Date).AddSeconds($GraceSec); while ((Get-Date) -lt $deadline) { $alive = @($procs | Where-Object { Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.ProcessId) -ErrorAction SilentlyContinue }); if ($alive.Count -eq 0) { break }; Start-Sleep -Seconds 1 }; $stillAlive = @($procs | Where-Object { Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.ProcessId) -ErrorAction SilentlyContinue }); if ($stillAlive.Count -gt 0) { Write-Host ('Graceful exit failed for ' + $stillAlive.Count + ' process(es); falling back to hard kill') } else { Write-Host 'All processes exited gracefully.' } }"

REM Phase 2: hard kill fallback. Identical to the original Terminate call;
REM any process that survived the grace window gets the same hard-kill
REM treatment the script used to apply to all matching processes.
powershell -NoProfile -Command "$pats = 'omniscribe.server:app', 'celery -A omniscribe.api.tasks', 'src.omniscribe.server:app', 'celery -A src.omniscribe.api.celery_app'; Get-CimInstance Win32_Process | Where-Object { $cl = $_.CommandLine; $pats | Where-Object { $cl -like ('*' + $_ + '*') } } | ForEach-Object { Write-Host ('Hard-killing PID ' + $_.ProcessId + ' (' + $_.Name + ')'); $_ | Invoke-CimMethod -MethodName Terminate | Out-Null }"

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
