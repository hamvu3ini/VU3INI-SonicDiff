@echo off
setlocal
title VU3INI SonicDiff - install
cd /d "%~dp0"
if /i "%~1"=="/repair" goto repair

set "DEST=C:\VU3INI\SonicDiff"
echo VU3INI SonicDiff 0.9.3
echo.
echo SonicDiff runs directly from this folder; installing is optional.
echo Install copies it to %DEST% (a short path avoids Windows' long-path limit)
echo and adds Desktop and Start-menu shortcuts. No administrator rights are needed
echo unless C:\VU3INI cannot be created by your account.
echo.
choice /m "Install to %DEST%"
if errorlevel 2 goto end
robocopy "%~dp0." "%DEST%" /E /NFL /NDL /NJH /NJS /NP /XD projects logs cache /XF Install.bat >nul
if %errorlevel% geq 8 (echo Copy failed. & pause & goto end)
copy /y "%~f0" "%DEST%\Install.bat" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=New-Object -ComObject WScript.Shell;" ^
  "foreach($d in @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))){" ^
  " $l=$s.CreateShortcut((Join-Path $d 'VU3INI SonicDiff.lnk')); $l.TargetPath='%DEST%\SonicDiff.exe'; $l.WorkingDirectory='%DEST%'; $l.IconLocation='%DEST%\SonicDiff.exe,0'; $l.Save();" ^
  " $b=$s.CreateShortcut((Join-Path $d 'VU3INI SonicDiff (browser).lnk')); $b.TargetPath='%DEST%\SonicDiff-Browser.exe'; $b.WorkingDirectory='%DEST%'; $b.IconLocation='%DEST%\SonicDiff.exe,0'; $b.Save() }"
echo.
echo Installed. Start SonicDiff from the Desktop shortcut.
pause
goto end

:repair
echo Reinstalling every library from the wheels folder (offline)...
"%~dp0python\python.exe" -m pip install --no-index --find-links "%~dp0wheels" --no-deps --force-reinstall --no-warn-script-location -r "%~dp0requirements-lock.txt"
echo Done.
pause
:end
endlocal
