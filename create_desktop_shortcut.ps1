$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "DataCapture.lnk"
$target = Join-Path $env:WINDIR "System32\wscript.exe"
$vbs = Join-Path $root "Launch DataCapture.vbs"
$icon = Join-Path $root "datacapture-launcher.ico"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.Arguments = "`"$vbs`""
$shortcut.WorkingDirectory = $root
if (Test-Path $icon) { $shortcut.IconLocation = "$icon,0" }
$shortcut.Description = "Start DataCapture"
$shortcut.Save()
Write-Host "Created desktop shortcut: $shortcutPath"
