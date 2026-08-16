$path = 'D:\OmniScribe\start_app.vbs'
$bytes = [System.IO.File]::ReadAllBytes($path)
$crlf = 0
$lfOnly = 0
for ($i = 0; $i -lt $bytes.Length; $i++) {
    if ($bytes[$i] -eq 13 -and ($i + 1) -lt $bytes.Length -and $bytes[$i + 1] -eq 10) {
        $crlf++
        $i++
    }
    elseif ($bytes[$i] -eq 10) {
        $lfOnly++
    }
}
Write-Host ("CRLF: " + $crlf + "  LF-only: " + $lfOnly + "  size: " + $bytes.Length)
