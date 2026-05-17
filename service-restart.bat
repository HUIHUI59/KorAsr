@echo off
REM service-restart.bat — stop + start
call "%~dp0service-stop.bat" --quiet
timeout /t 2 /nobreak >nul
call "%~dp0service-start.bat" --quiet
echo.
echo Restart complete.
pause
