@echo off
REM service-enable-autostart.bat — Register the backend to launch on user logon
REM Needs admin: right-click -> Run as administrator
echo Registering "KorASR Backend" task (triggers at user logon)...
schtasks /Create /TN "KorASR Backend" /TR "\"%~dp0service-start.bat\" --quiet" /SC ONLOGON /RL HIGHEST /F
if errorlevel 1 (
  echo.
  echo [FAILED] schtasks returned non-zero.
  echo  - Most common cause: not running as administrator.
  echo  - Right-click this .bat and pick "Run as administrator", then try again.
) else (
  echo.
  echo [OK] Autostart enabled. KorASR will start hidden on next login.
  echo      Verify: service-status.bat
)
pause
