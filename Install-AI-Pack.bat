@echo off
title VU3INI SonicDiff - install AI pack
cd /d "%~dp0"
echo This installs voice separation (audio-separator + BS-RoFormer model) and Beat This!
echo with PyTorch for your NVIDIA GPU (CUDA 12.8) or for the CPU.
echo.
echo If an "ai_pack" folder made by Make-Offline-AI-Pack.bat is next to this file, no internet is needed.
echo Otherwise about 3-4 GB is downloaded once.
echo.
pause
"%~dp0python\python.exe" "%~dp0app\sonicdiff\ai_pack.py"
echo.
pause
