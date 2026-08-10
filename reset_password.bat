@echo off
setlocal
title DataCapture Password Reset
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add Python to PATH" during installation.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating local virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
  )
)

set "PY=%CD%\.venv\Scripts\python.exe"
"%PY%" -c "import flask, waitress" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies into .venv ^(first run only^)...
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
  )
)

"%PY%" reset_admin_password.py
pause
