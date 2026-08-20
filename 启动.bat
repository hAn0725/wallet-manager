@echo off
cd /d "%~dp0"

rem Use the project virtualenv if present (does not depend on uv in PATH)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m app.main
    goto :after
)

rem Fallback: try uv
where uv >nul 2>nul
if errorlevel 1 (
    echo [Error] Cannot find Python or uv.
    echo Open a terminal in this folder and run:  uv sync
    echo.
    pause
    exit /b 1
)
uv run python -m app.main

:after
if errorlevel 1 (
    echo.
    echo Program exited with an error. Press any key to close.
    pause >nul
)
