@echo off
title VU3INI SonicDiff
cd /d "%~dp0"
echo Starting VU3INI SonicDiff in your web browser...
echo Keep this window open while you work. Close it to stop SonicDiff.
"%~dp0python\python.exe" "%~dp0app\run.py" --browser
if errorlevel 1 pause
