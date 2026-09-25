@echo off
title Video Studio Pro - Mobile Server
cd /d "%~dp0"
echo ========================================================
echo   Video Studio Pro - Mobile Edition Server
echo ========================================================
echo.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -X utf8 mobile_app.py
) else (
    python -X utf8 mobile_app.py
)
pause
