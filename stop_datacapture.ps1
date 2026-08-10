$ErrorActionPreference = "SilentlyContinue"
Add-Type -AssemblyName System.Windows.Forms
$port = 8710

function Get-DataCapturePids {
    $pids = @()
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) { $pids += [int]$c.OwningProcess }
    } catch {
        $lines = netstat -ano | Select-String ":$port\s.*LISTENING"
        foreach ($ln in $lines) {
            $parts = ($ln.ToString().Trim() -split "\s+")
            $pids += [int]$parts[-1]
        }
    }
    return ($pids | Sort-Object -Unique)
}

$killed = $false
foreach ($procId in (Get-DataCapturePids)) {
    if ($procId -le 0) { continue }
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($p -and ($p.ProcessName -match "python")) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        $killed = $true
    }
}

if ($killed) {
    [System.Windows.Forms.MessageBox]::Show("DataCapture has been stopped.", "DataCapture") | Out-Null
} else {
    [System.Windows.Forms.MessageBox]::Show("DataCapture was not running.", "DataCapture") | Out-Null
}
