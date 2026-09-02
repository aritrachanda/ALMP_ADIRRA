@echo off
REM ADIRRA dev stopper — companion to start-dev.bat. Stops the backend (port 8000)
REM and frontend (port 9000) dev servers with one double-click. Works the same
REM whether they were started hidden or in a visible window, since it kills
REM by owning process of the port, not by window.

echo Stopping backend (port 8000) if running...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo Stopping frontend (port 9000) if running...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 9000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo Done.
pause
