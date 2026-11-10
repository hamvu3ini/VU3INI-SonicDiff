@echo off
title VU3INI SonicDiff self-test
cd /d "%~dp0app"
echo Running the SonicDiff self-test (about one minute)...
"%~dp0python\python.exe" -m sonicdiff.selftest
echo.
pause
