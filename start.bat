@echo off
title Google Flow Auto Prompter & Downloader
echo =======================================================
echo   Google Flow / ImageFX Auto-Prompter and Downloader
echo =======================================================
echo.
echo Launching GUI Application...
python app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred. Installing dependencies...
    pip install playwright PySide6 pillow
    playwright install chromium
    python app.py
)
pause
