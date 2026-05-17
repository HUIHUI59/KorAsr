@echo off
REM service-start.bat — Hidden background launch of KorASR backend.
REM Logs land in logs\service.log. Pass --quiet to skip the final pause
REM (used by service-restart.bat and the autostart Task Scheduler entry).
setlocal
set "PROJ=%~dp0"
if not exist "%PROJ%logs" mkdir "%PROJ%logs"

REM Kill any existing listener on 8000 so this is idempotent
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }"
timeout /t 1 /nobreak >nul

REM Detached, hidden, all PS streams redirected to log
start "" /B powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "& { Set-Location '%PROJ%'; & '.\startAll.ps1' -NoBuild *> '%PROJ%logs\service.log' }"

echo KorASR backend launched (hidden).
echo   Log:  %PROJ%logs\service.log
echo   URL:  https://localhost:8000
echo         https://100.95.4.120:8000  (Tailscale)
echo.
if /I not "%~1"=="--quiet" pause
endlocal
