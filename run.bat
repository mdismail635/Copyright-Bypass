@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" video_studio_pro.py
) else (
    python video_studio_pro.py
    pause
)
