@echo off
setlocal
title DataCapture
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_datacapture.ps1"
