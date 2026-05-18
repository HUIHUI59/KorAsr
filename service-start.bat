@echo off
REM service-start.bat - launch KorASR backend detached.
REM Pass --quiet to skip pause (used by service-restart.bat and autostart task).
REM
REM Detach via PowerShell Start-Process -WindowStyle Hidden, WITHOUT
REM -RedirectStandardOutput (the two flags conflict in Windows PowerShell 5.1
REM and kill python on spawn). Python writes its own logs to logs/service.log
REM via a Tee installed at the top of start.py.
setlocal
set "PROJ=%~dp0"
if not exist "%PROJ%logs" mkdir "%PROJ%logs"

REM 1) Kill prior listener on 8000 (idempotent)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
ping -n 2 127.0.0.1 >nul

REM 2) Launch detached. Env vars set inside the child PowerShell so they're
REM    inherited by python. No redirect flags - python's Tee handles logging.
powershell -NoProfile -Command "$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; Start-Process -FilePath '%PROJ%venv\Scripts\python.exe' -ArgumentList '%PROJ%start.py' -WorkingDirectory '%PROJ%' -WindowStyle Hidden"

echo KorASR backend launched (detached background).
echo   log:  %PROJ%logs\service.log
echo   URL:  https://localhost:8000
echo         https://100.95.4.120:8000  (Tailscale)
echo.
if /I not "%~1"=="--quiet" pause
endlocal
