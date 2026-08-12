' start_app.vbs -- boot Redis (Docker), Celery, and the OmniScribe web server.
' Designed to be safe to re-run on every login / shortcut click.

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Change working directory so uv and the app resolve project-relative paths.
objShell.CurrentDirectory = scriptDir

' --- Logging (append; safe across reboots) ---
Const ForAppending = 8
Dim logFile : Set logFile = objFSO.OpenTextFile(scriptDir & "\start_app.log", ForAppending, True)

Sub LogMsg(s)
    logFile.WriteLine FormatDateTime(Now, vbGeneralDate) & " " & s
End Sub

LogMsg "===== start_app.vbs launched (cwd=" & scriptDir & ") ====="

' --- Helpers ---
Function IsDockerAvailable()
    On Error Resume Next
    Dim exec : Set exec = objShell.Exec("docker info")
    Do While exec.Status = 0 : WScript.Sleep 100 : Loop
    IsDockerAvailable = (exec.ExitCode = 0)
    On Error Goto 0
End Function

Function ContainerExists(name)
    On Error Resume Next
    Dim exec : Set exec = objShell.Exec("docker inspect " & name)
    Do While exec.Status = 0 : WScript.Sleep 100 : Loop
    ContainerExists = (exec.ExitCode = 0)
    On Error Goto 0
End Function

' --- 0. Pre-check: uv must be on PATH (added by the official uv installer
'     to the user PATH; needs a fresh logon to propagate). ---
On Error Resume Next
Dim uvCheck : Set uvCheck = objShell.Exec("uv --version")
Do While uvCheck.Status = 0 : WScript.Sleep 100 : Loop
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
    If ContainerExists("redis-local-ocr") Then
        LogMsg "Reusing existing redis-local-ocr container (docker start)"
        objShell.Run "cmd.exe /c docker start redis-local-ocr", 0, True
    Else
        LogMsg "Creating new redis-local-ocr container (docker run --rm)"
        objShell.Run "cmd.exe /c docker run -d --name redis-local-ocr -p 6379:6379 --rm redis", 0, True
    End If

    ' --- 2. Celery worker (hidden, fire-and-forget) ---
    LogMsg "Starting Celery worker"
    objShell.Run "cmd.exe /c uv run --extra web celery -A src.omniscribe.api.celery_app worker --loglevel=info -P solo", 0, False
Else
    LogMsg "Docker is not available; skipping Redis and Celery. Async translation will be disabled."
End If

' --- 3. uvicorn (hidden, fire-and-forget) ---
LogMsg "Starting uvicorn on :8000"
objShell.Run "cmd.exe /c uv run --extra web uvicorn src.omniscribe.server:app --port 8000", 0, False

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
