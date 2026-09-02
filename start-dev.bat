@echo off
REM ADIRRA dev launcher (silent) — starts backend + frontend completely hidden
REM (no visible console windows at all). Output goes to logs\backend.log /
REM logs\frontend.log so you can still check what happened if something
REM fails to start. Use stop-dev.bat to stop both.
REM
REM Backend is skipped if something is already listening on port 8000 —
REM DuckDB is single-writer, so a second instance would corrupt
REM governance/dq_scores.yaml (see AGENTS.md "Critical gotchas").

setlocal
set "REPO_ROOT=%~dp0"
if not exist "%REPO_ROOT%logs" mkdir "%REPO_ROOT%logs"

echo Checking whether a backend is already running on port 8000...
netstat -ano | findstr /R /C:"LISTENING" | findstr ":8000 " >nul
if %errorlevel%==0 (
    echo A process is already listening on port 8000 - skipping backend start.
    echo ^(Only one backend instance may run at a time - see AGENTS.md.^)
) else (
    echo Starting backend ^(hidden^) on http://localhost:8000 ...
    powershell -NoProfile -Command "Start-Process -FilePath '%REPO_ROOT%.venv\Scripts\uvicorn.exe' -ArgumentList 'api.main:app','--port','8000' -WorkingDirectory '%REPO_ROOT%' -WindowStyle Hidden -RedirectStandardOutput '%REPO_ROOT%logs\backend.log' -RedirectStandardError '%REPO_ROOT%logs\backend.err.log'"
)

echo Starting frontend ^(hidden^) on http://localhost:9000 ...
powershell -NoProfile -Command "Start-Process -FilePath 'npm.cmd' -ArgumentList 'run','dev' -WorkingDirectory '%REPO_ROOT%frontend' -WindowStyle Hidden -RedirectStandardOutput '%REPO_ROOT%logs\frontend.log' -RedirectStandardError '%REPO_ROOT%logs\frontend.err.log'"

echo Waiting for the dev servers to warm up...
timeout /t 6 /nobreak >nul

echo Opening the app...
start http://localhost:9000/home

echo Both servers are running in the background - no window to close.
echo Logs (if something looks wrong): logs\backend.log / logs\frontend.log
echo Use stop-dev.bat to stop them.
endlocal
