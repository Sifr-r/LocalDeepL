' start_app.vbs -- boot Redis (Docker), Celery, and the OmniScribe web server.
' Designed to be safe to re-run on every login / shortcut click.

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Change working directory so uv and the app resolve project-relative paths.
objShell.CurrentDirectory = scriptDir

' --- Logging (append; safe across reboots) ---
Const ForAppending = 8

' --- Polling loop bounds (M3 audit): cap each unbounded Do-While loop so a
'     hung external process (docker.exe, uv.exe) cannot stall the launcher.
'     Defaults: 300 attempts * 100ms = 30s wall-clock per check. Tune via
'     the two Consts below; success-path behaviour is byte-identical. ---
Const MAX_POLL_ATTEMPTS = 300
Const POLL_INTERVAL_MS = 100

Dim logFile : Set logFile = objFSO.OpenTextFile(scriptDir & "\start_app.log", ForAppending, True)

Sub LogMsg(s)
    logFile.WriteLine FormatDateTime(Now, vbGeneralDate) & " " & s
End Sub

LogMsg "===== start_app.vbs launched (cwd=" & scriptDir & ") ====="

' --- Helpers ---
Function IsDockerAvailable()
    On Error Resume Next
    Dim exec : Set exec = objShell.Exec("docker info")
    Dim attempts : attempts = 0
    Do While exec.Status = 0
        WScript.Sleep POLL_INTERVAL_MS
        attempts = attempts + 1
        If attempts >= MAX_POLL_ATTEMPTS Then
            LogMsg "FATAL: 'docker info' did not exit within " & (MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS / 1000) & "s; aborting launcher"
            logFile.Close
            WScript.Quit 1
        End If
    Loop
    IsDockerAvailable = (exec.ExitCode = 0)
    On Error Goto 0
End Function

Function ContainerExists(name)
    On Error Resume Next
    Dim exec : Set exec = objShell.Exec("docker inspect " & name)
    Dim attempts : attempts = 0
    Do While exec.Status = 0
        WScript.Sleep POLL_INTERVAL_MS
        attempts = attempts + 1
        If attempts >= MAX_POLL_ATTEMPTS Then
            LogMsg "FATAL: 'docker inspect " & name & "' did not exit within " & (MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS / 1000) & "s; aborting launcher"
            logFile.Close
            WScript.Quit 1
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
    Dim pwd, psCmd, exec, attempts
    psCmd = "powershell -NoProfile -NonInteractive -Command ""$alphabet = [char[]]'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'; $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create(); $bytes = New-Object byte[] 24; $rng.GetBytes($bytes); -join ($bytes | ForEach-Object { $alphabet[[int]($_ % 62)] })"""
    Set exec = objShell.Exec(psCmd)
    attempts = 0
    Do While exec.Status = 0
        WScript.Sleep POLL_INTERVAL_MS
        attempts = attempts + 1
        If attempts >= MAX_POLL_ATTEMPTS Then
            LogMsg "FATAL: PowerShell CSPRNG did not exit within " & (MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS / 1000) & "s; aborting launcher"
            logFile.Close
            WScript.Quit 1
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
Do While uvCheck.Status = 0
    WScript.Sleep POLL_INTERVAL_MS
    uvAttempts = uvAttempts + 1
    If uvAttempts >= MAX_POLL_ATTEMPTS Then
        LogMsg "FATAL: 'uv --version' did not exit within " & (MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS / 1000) & "s; aborting launcher (uv hung?)"
        logFile.Close
        MsgBox "uv --version did not respond within " & (MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS / 1000) & " seconds." & vbCrLf & vbCrLf & _
               "This usually means uv is installed but hung, or the executable is blocked by antivirus." & vbCrLf & _
               "Try opening a new Command Prompt and running 'uv --version' manually to diagnose.", _
               vbCritical, "OmniScribe"
        WScript.Quit 1
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

    ' --- 2. Celery worker (hidden, fire-and-forget) ---
    ' -A must use the installed-package module path (compose.yaml uses the
    ' same). The old `src.*` namespace form resolved a second module copy,
    ' so tasks registered on the `omniscribe.*` copy were invisible to the
    ' worker (audit DevOps High #6, drift half).
    LogMsg "Starting Celery worker"
    objShell.Run "cmd.exe /c set ""REDIS_URL=" & redisUrl & """" & " && uv run --extra web celery -A omniscribe.api.tasks worker --loglevel=info -P solo", 0, False
Else
    LogMsg "Docker is not available; skipping Redis and Celery. Async translation will be disabled."
End If

' --- 3. uvicorn (hidden, fire-and-forget) ---
' Same installed-package path as the `omniscribe-server` console script so
' the API process imports one module copy, not a `src.*` namespace twin.
LogMsg "Starting uvicorn on :8000"
If dockerUp Then
    objShell.Run "cmd.exe /c set ""REDIS_URL=" & redisUrl & """" & " && uv run --extra web uvicorn omniscribe.server:app --port 8000", 0, False
Else
    objShell.Run "cmd.exe /c uv run --extra web uvicorn omniscribe.server:app --port 8000", 0, False
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
