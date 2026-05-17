@echo off
REM service-stop.bat — Kill whoever is holding port 8000. Pass --quiet to skip pause.
echo Stopping KorASR backend (port 8000)...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if ($c) { $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue; if ($p) { Write-Host ('Killing PID=' + $p.Id + ' (' + $p.ProcessName + ')'); Stop-Process -Id $p.Id -Force; Write-Host 'Stopped.' -ForegroundColor Green } else { Write-Host ('Port 8000 held by PID=' + $c.OwningProcess + ' but process info unavailable.') -ForegroundColor Yellow } } else { Write-Host 'Not running (port 8000 free).' -ForegroundColor Yellow }"
if /I not "%~1"=="--quiet" pause
