@echo off
setlocal
cd /d "%~dp0.."
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8765"
set "PY=%CD%\.venv_mace\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
start "" "http://127.0.0.1:%PORT%"
"%PY%" "one_click_mof\app.py" --port %PORT%
