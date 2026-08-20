' start_app.vbs -- boot Redis (Docker), Celery, and the OmniScribe web server.
' Designed to be safe to re-run on every login / shortcut click.

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Change working directory so uv and the app resolve project-relative paths.
objShell.CurrentDirectory = scriptDir

' --- Logging (append; safe across reboots) ---
Const ForAppending = 8

' --- Log rotation (audit-secondary Phase 5 — F23): the launcher can be
'     re-run on every login / shortcut click, and a long-running station
'     that boots daily can grow start_app.log into the hundreds of MB
'     over a year. Rotate when the file crosses MAX_LOG_BYTES; keep
'     MAX_LOG_BACKUPS generations (start_app.log.1 .. .MAX_LOG_BACKUPS).
'     The oldest backup is dropped on each rotation. ---
Const MAX_LOG_BYTES = 10485760     ' 10 MiB
Const MAX_LOG_BACKUPS = 3
Const LOG_BASE_NAME = "start_app.log"

' --- Polling loop bounds (M3 audit): cap each unbounded Do-While loop so a
'     hung external process (docker.exe, uv.exe) cannot stall the launcher.
'     MAX_POLL_ATTEMPTS bounds the iteration count; success-path behaviour
'     is identical to the pre-F30 fixed 100ms sleep on the first poll. ---
'
'     Adaptive backoff (audit-secondary Phase 5 — F30): instead of a fixed
'     100ms sleep, start fast (INITIAL_BACKOFF_MS) and double on each
'     iteration up to a 2s cap (MAX_BACKOFF_MS). This keeps the success
'     path snappy (most polls hit on the first or second iteration) while
'     avoiding a tight loop when the child is truly hung. The wall-clock
'     upper bound is ~10 minutes at the cap; a hung child still fails
'     fast relative to a human operator waiting on the launcher.
Const MAX_POLL_ATTEMPTS = 300
Const INITIAL_BACKOFF_MS = 100
Const MAX_BACKOFF_MS = 2000

' Rotate start_app.log if it has crossed MAX_LOG_BYTES. Rolls
' start_app.log.N -> start_app.log.(N+1), dropping the oldest, then
' creates a fresh start_app.log. No-op on first launch when no log
' exists yet.
Sub RotateLogIfNeeded()
    Dim logPath : logPath = scriptDir & "\" & LOG_BASE_NAME
    If Not objFSO.FileExists(logPath) Then Exit Sub
    Dim f : Set f = objFSO.GetFile(logPath)
    If f.Size < MAX_LOG_BYTES Then Exit Sub
    f.Close
    ' Shift backups: .MAX -> delete, .(N) -> .(N+1), ..., .1 -> .2
    Dim oldest : oldest = scriptDir & "\" & LOG_BASE_NAME & "." & MAX_LOG_BACKUPS
    If objFSO.FileExists(oldest) Then objFSO.DeleteFile oldest, True
    Dim i
    For i = MAX_LOG_BACKUPS - 1 To 1 Step -1
        Dim src : src = scriptDir & "\" & LOG_BASE_NAME & "." & i
        Dim dst : dst = scriptDir & "\" & LOG_BASE_NAME & "." & (i + 1)
        If objFSO.FileExists(src) Then
            objFSO.MoveFile src, dst
        End If
    Next
    ' .log -> .1
    objFSO.MoveFile logPath, scriptDir & "\" & LOG_BASE_NAME & ".1"
End Sub

RotateLogIfNeeded

Dim logFile : Set logFile = objFSO.OpenTextFile(scriptDir & "\" & LOG_BASE_NAME, ForAppending, True)

Sub LogMsg(s)
    logFile.WriteLine FormatDateTime(Now, vbGeneralDate) & " " & s
End Sub

LogMsg "===== start_app.vbs launched (cwd=" & scriptDir & ") ====="

' --- Helpers ---
Function IsDockerAvailable()
    On Error Resume Next
    Dim exec : Set exec = objShell.Exec("docker info")
    Dim attempts : attempts = 0
    Dim backoff : backoff = INITIAL_BACKOFF_MS
    Do While exec.Status = 0
        WScript.Sleep backoff
        attempts = attempts + 1
        If attempts >= MAX_POLL_ATTEMPTS Then
            LogMsg "FATAL: 'docker info' did not exit within " & (MAX_POLL_ATTEMPTS * INITIAL_BACKOFF_MS / 1000) & "s; aborting launcher"
            logFile.Close
            WScript.Quit 1
        End If
        If backoff < MAX_BACKOFF_MS Then
            backoff = backoff * 2
            If backoff > MAX_BACKOFF_MS Then backoff = MAX_BACKOFF_MS
        End If
    Loop
    IsDockerAvailable = (exec.ExitCode = 0)
    On Error Goto 0
End Function

Function ContainerExists(name)
    On Error Resume Next
    Dim exec : Set exec = objShell.Exec("docker inspect " & name)
    Dim attempts : attempts = 0
    Dim backoff : backoff = INITIAL_BACKOFF_MS
    Do While exec.Status = 0
        WScript.Sleep backoff
        attempts = attempts + 1
        If attempts >= MAX_POLL_ATTEMPTS Then
            LogMsg "FATAL: 'docker inspect " & name & "' did not exit within " & (MAX_POLL_ATTEMPTS * INITIAL_BACKOFF_MS / 1000) & "s; aborting launcher"
            logFile.Close
            WScript.Quit 1
        End If
        If backoff < MAX_BACKOFF_MS Then
            backoff = backoff * 2
            If backoff > MAX_BACKOFF_MS Then backoff = MAX_BACKOFF_MS
        End If
    Loop
    ContainerExists = (exec.ExitCode = 0)
    On Error Goto 0
End Function

' --- Redis password (audit P1-6): generated once, kept next to this
'     script, never logged. Reused on every subsequent launch so Celery
'     and uvicorn can rebuild the same REDIS_URL. ---
Function GetOrCreateRedisPassword()
    Dim passPath : passPath = scriptDir & "\redis-password.txt"
    If objFSO.FileExists(passPath) Then
        Dim f : Set f = objFSO.OpenTextFile(passPath, 1)
        GetOrCreateRedisPassword = Trim(f.ReadLine())
        f.Close
        Exit Function
    End If
    ' Generate a 24-character password using the .NET CSPRNG. The previous
    ' implementation used the VBScript built-in PRNG (an LCG seeded by the
    ' wall clock), which is guessable in shared environments even with
    ' --requirepass set on the Redis side. sh.Exec is the portable form for
    ' capturing stdout; sh.Run only returns the exit code.
    Dim pwd, psCmd, exec, attempts, backoff
    psCmd = "powershell -NoProfile -NonInteractive -Command ""$alphabet = [char[]]'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'; $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create(); $bytes = New-Object byte[] 24; $rng.GetBytes($bytes); -join ($bytes | ForEach-Object { $alphabet[[int]($_ % 62)] })"""
    Set exec = objShell.Exec(psCmd)
    attempts = 0
    backoff = INITIAL_BACKOFF_MS
    Do While exec.Status = 0
        WScript.Sleep backoff
        attempts = attempts + 1
        If attempts >= MAX_POLL_ATTEMPTS Then
            LogMsg "FATAL: PowerShell CSPRNG did not exit within " & (MAX_POLL_ATTEMPTS * INITIAL_BACKOFF_MS / 1000) & "s; aborting launcher"
            logFile.Close
            WScript.Quit 1
        End If
        If backoff < MAX_BACKOFF_MS Then
            backoff = backoff * 2
            If backoff > MAX_BACKOFF_MS Then backoff = MAX_BACKOFF_MS
        End If
    Loop
    pwd = exec.StdOut.ReadAll()
    pwd = Replace(pwd, vbCrLf, "")
    pwd = Replace(pwd, vbLf, "")
    If Len(pwd) <> 24 Then
        LogMsg "FATAL: PowerShell CSPRNG returned unexpected length " & Len(pwd) & " (expected 24); aborting launcher"
        logFile.Close
        WScript.Quit 1
    End If
    Dim nf : Set nf = objFSO.OpenTextFile(passPath, 2, True)
    nf.WriteLine pwd
    nf.Close
    GetOrCreateRedisPassword = pwd
End Function

' --- 0. Pre-check: uv must be on PATH (added by the official uv installer
'     to the user PATH; needs a fresh logon to propagate). ---
On Error Resume Next
Dim uvCheck : Set uvCheck = objShell.Exec("uv --version")
Dim uvAttempts : uvAttempts = 0
Dim uvBackoff : uvBackoff = INITIAL_BACKOFF_MS
Do While uvCheck.Status = 0
    WScript.Sleep uvBackoff
    uvAttempts = uvAttempts + 1
    If uvAttempts >= MAX_POLL_ATTEMPTS Then
        LogMsg "FATAL: 'uv --version' did not exit within " & (MAX_POLL_ATTEMPTS * INITIAL_BACKOFF_MS / 1000) & "s; aborting launcher (uv hung?)"
        logFile.Close
        MsgBox "uv --version did not respond within " & (MAX_POLL_ATTEMPTS * INITIAL_BACKOFF_MS / 1000) & " seconds." & vbCrLf & vbCrLf & _
               "This usually means uv is installed but hung, or the executable is blocked by antivirus." & vbCrLf & _
               "Try opening a new Command Prompt and running 'uv --version' manually to diagnose.", _
               vbCritical, "OmniScribe"
        WScript.Quit 1
    End If
    If uvBackoff < MAX_BACKOFF_MS Then
        uvBackoff = uvBackoff * 2
        If uvBackoff > MAX_BACKOFF_MS Then uvBackoff = MAX_BACKOFF_MS
    End If
Loop
If uvCheck.ExitCode <> 0 Then
    LogMsg "FATAL: uv is not on PATH; aborting before launching services"
    logFile.Close
    MsgBox "uv is not on your PATH." & vbCrLf & vbCrLf & _
           "If you just installed OmniScribe, log out of Windows and back in (or reboot) so the PATH update takes effect, then re-run this shortcut." & vbCrLf & vbCrLf & _
           "If uv is genuinely missing, run install.bat again.", _
           vbCritical, "OmniScribe"
    WScript.Quit 1
End If
On Error Goto 0
LogMsg "uv is on PATH"

' --- 1. Redis (only if Docker is reachable) ---
Dim dockerUp : dockerUp = IsDockerAvailable()
If dockerUp Then
    LogMsg "Docker daemon is reachable"
    Dim redisPass : redisPass = GetOrCreateRedisPassword()
    Dim redisUrl : redisUrl = "redis://:" & redisPass & "@localhost:6379/0"
    ' Always recreate: the container holds only ephemeral broker state
    ' (--rm + --save ""), and recreating guarantees the hardened flags
    ' (pinned image, loopback bind, requirepass) even for containers
    ' created by older versions of this script.
    If ContainerExists("redis-local-ocr") Then
        LogMsg "Removing pre-hardening redis-local-ocr container"
        objShell.Run "cmd.exe /c docker rm -f redis-local-ocr", 0, True
    End If
    LogMsg "Creating hardened redis-local-ocr container (pinned image, loopback-only, requirepass)"
    objShell.Run "cmd.exe /c docker run -d --name redis-local-ocr -p 127.0.0.1:6379:6379 --rm redis:7-alpine redis-server --appendonly no --save """" --requirepass " & redisPass, 0, True

    ' --- 2. Celery worker (visible terminal, fire-and-forget) ---
    ' -A must use the installed-package module path (compose.yaml uses the
    ' same). The old `src.*` namespace form resolved a second module copy,
    ' so tasks registered on the `omniscribe.*` copy were invisible to the
    ' worker (audit DevOps High #6, drift half).
    LogMsg "Starting Celery worker in terminal"
    objShell.Run "cmd.exe /k title OmniScribe Celery Worker && set ""REDIS_URL=" & redisUrl & """" & " && uv run --extra web --extra async-translation celery -A omniscribe.api.tasks worker --loglevel=info -P solo", 1, False
Else
    LogMsg "Docker is not available; skipping Redis and Celery. Async translation will be disabled."
End If

' --- 3. uvicorn (visible terminal, fire-and-forget) ---
' Same installed-package path as the `omniscribe-server` console script so
' the API process imports one module copy, not a `src.*` namespace twin.
LogMsg "Starting uvicorn on :8000 in terminal"
If dockerUp Then
    objShell.Run "cmd.exe /k title OmniScribe Server && set ""REDIS_URL=" & redisUrl & """" & " && uv run --extra web uvicorn omniscribe.server:app --port 8000", 1, False
Else
    objShell.Run "cmd.exe /k title OmniScribe Server && uv run --extra web uvicorn omniscribe.server:app --port 8000", 1, False
End If

' --- 4. Wait for uvicorn to actually respond (poll HTTP, max 60s) ---
LogMsg "Waiting for uvicorn to respond on http://localhost:8000"
Dim waited : waited = 0
Dim ready : ready = False
Do
    WScript.Sleep 1000
    waited = waited + 1
    Dim http : Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    On Error Resume Next
    http.SetTimeouts 1500, 1500, 1500, 1500
    http.Open "GET", "http://localhost:8000/", False
    http.Send
    If Err.Number = 0 Then
        ' Treat any non-5xx as "server is up" -- a 404 still means uvicorn answered.
        If http.Status < 500 Then ready = True End If
    End If
    On Error Goto 0
    Set http = Nothing
    If ready Or waited >= 60 Then Exit Do
Loop

If ready Then
    LogMsg "Server responded after " & waited & "s; opening browser"
Else
    LogMsg "Server did not respond within 60s; opening browser anyway (check uvicorn output if the UI never loads)"
End If

' --- 5. Open Web UI ---
objShell.Run "http://localhost:8000"

logFile.Close
