@echo off
REM service-disable-autostart.bat — Remove the Task Scheduler entry
echo Removing "KorASR Backend" task...
schtasks /Delete /TN "KorASR Backend" /F
if errorlevel 1 (
  echo [INFO] Task did not exist or could not be deleted.
) else (
  echo [OK] Autostart disabled.
)
pause
