$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$port = 8710
$url = "http://localhost:$port"

function Test-DataCapturePort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect("127.0.0.1", $port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(200, $false)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-DataCapturePids {
    # Process IDs currently listening on our port.
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

function Stop-DataCapture {
    # Stop any running DataCapture server so the newest code loads.
    foreach ($procId in (Get-DataCapturePids)) {
        if ($procId -le 0) { continue }
        try {
            $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($p -and ($p.ProcessName -match "python")) {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
    for ($i = 0; $i -lt 40; $i++) {
        if (-not (Test-DataCapturePort)) { return }
        Start-Sleep -Milliseconds 150
    }
}

# --- Ensure Python + virtual environment ---
if (-not (Test-Path $python)) {
    $globalPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $globalPython) {
        [System.Windows.Forms.MessageBox]::Show(
            "Python was not found. Install Python 3.10+ and tick Add Python to PATH.",
            "DataCapture") | Out-Null
        exit 1
    }
    Start-Process -FilePath $globalPython -ArgumentList @("-m", "venv", ".venv") -WorkingDirectory $root -WindowStyle Hidden -Wait
}

& $python -c "import flask, waitress, numpy, pandas, scipy, statsmodels, pyreadstat" *> $null
if ($LASTEXITCODE -ne 0) {
    Start-Process -FilePath $python -ArgumentList @("-m", "pip", "install", "-r", "requirements.txt") -WorkingDirectory $root -WindowStyle Hidden -Wait
}

if (-not (Test-Path $pythonw)) { $pythonw = $python }

# --- Always restart so a double-click loads the latest code (no Task Manager) ---
Stop-DataCapture

Start-Process -FilePath $pythonw -ArgumentList @("server_hidden.py") -WorkingDirectory $root -WindowStyle Hidden | Out-Null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 250
    if (Test-DataCapturePort) { break }
}

if (Test-DataCapturePort) {
    Start-Process $url
} else {
    [System.Windows.Forms.MessageBox]::Show(
        "DataCapture did not start. Check data\launcher.log in the DataCapture folder.",
        "DataCapture") | Out-Null
    exit 1
}
