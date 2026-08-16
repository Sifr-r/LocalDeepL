$deadline = (Get-Date).AddSeconds(300)
$up = $false
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri 'http://localhost:8000/health' -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -lt 500) { $up = $true; break }
    } catch { }
    Start-Sleep -Seconds 5
}
if ($up) {
    Write-Output 'SERVER UP: http://localhost:8000/health responded'
} else {
    Write-Output 'SERVER STILL DOWN after 300s'
    Write-Output '--- live uv/python processes ---'
    Get-Process uv, python, uvicorn -ErrorAction SilentlyContinue |
        Select-Object Id, ProcessName, @{n = 'CPU_s'; e = { [math]::Round($_.CPU, 1) } } |
        Format-Table -AutoSize | Out-String | Write-Output
}
