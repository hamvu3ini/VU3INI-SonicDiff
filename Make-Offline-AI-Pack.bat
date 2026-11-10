@echo off
title VU3INI SonicDiff - make offline AI pack
cd /d "%~dp0"
echo Downloads the AI pack into an "ai_pack" folder so it can be installed later without internet.
pause
"%~dp0python\python.exe" "%~dp0app\sonicdiff\ai_pack.py" --make-offline
pause
