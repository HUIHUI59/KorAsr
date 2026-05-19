@echo off
REM service-start.bat - launch KorASR backend detached.
REM Pass --quiet to skip pause (used by service-restart.bat and autostart task).
REM
REM Use pythonw.exe (NOT python.exe). python.exe is a console subsystem app:
REM even with -WindowStyle Hidden it inherits the parent console handle, so
REM when the launching cmd / SSH session exits the child receives
REM CTRL_CLOSE_EVENT and dies. pythonw.exe is a GUI-subsystem build with no
REM console attachment, so the detached process truly survives the launcher.
REM Logging still works because start.py installs a Tee that writes everything
REM to logs/service.log via a real file handle.
setlocal
set "PROJ=%~dp0"
if not exist "%PROJ%logs" mkdir "%PROJ%logs"

REM 1) Kill prior listener on 8000 (idempotent)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
ping -n 2 127.0.0.1 >nul

REM 2) Launch detached via pythonw (no console attachment, survives launcher exit).
REM    Env vars set inside the child PowerShell so they're inherited by pythonw.
powershell -NoProfile -Command "$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; Start-Process -FilePath '%PROJ%venv\Scripts\pythonw.exe' -ArgumentList '%PROJ%start.py' -WorkingDirectory '%PROJ%'"

echo KorASR backend launched (detached background).
echo   log:  %PROJ%logs\service.log
echo   URL:  https://localhost:8000
echo         https://100.95.4.120:8000  (Tailscale)
echo.
if /I not "%~1"=="--quiet" pause
endlocal
