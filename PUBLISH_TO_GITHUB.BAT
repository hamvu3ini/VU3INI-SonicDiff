@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title VU3INI SonicDiff - publish to GitHub
cd /d "%~dp0"

set "VER=0.9.3"
set "REPO=VU3INI-SonicDiff"
set "DESC=VU3INI SonicDiff: cross-tradition vocal acoustic comparison (Borgeet, Bhaona, Hindustani raga, Western opera)"

echo ==================================================================
echo   VU3INI SonicDiff %VER% - publish to GitHub
echo   By Sasanka Boruah -VU3INI
echo ==================================================================
echo.
echo This uploads the SonicDiff SOURCE CODE to a GitHub repository:
echo   app\, launchers, .bat scripts, README, LICENSE and licence notices.
echo.
echo It does NOT upload the large or private folders:
echo   python\, wheels\, bin\, models\, ai_pack\, projects\ (your studies),
echo   logs\, cache\ and settings.json  (see .gitignore).
echo.
echo You need Git for Windows. GitHub CLI (gh) is optional: with it, the
echo repository is created for you; without it, you create it on github.com.
echo.
pause

rem ------------------------------------------------------------------ git present?
where git >nul 2>&1
if errorlevel 1 goto :nogit
for /f "delims=" %%v in ('git --version') do echo Found %%v
echo.

rem ------------------------------------------------------------------ commit identity
set "GNAME="
set "GMAIL="
for /f "delims=" %%a in ('git config --global user.name 2^>nul') do set "GNAME=%%a"
for /f "delims=" %%a in ('git config --global user.email 2^>nul') do set "GMAIL=%%a"
if not defined GNAME (
  set /p "GNAME=Your name for commits (for example Sasanka Boruah): "
  if not defined GNAME set "GNAME=VU3INI"
  git config --global user.name "!GNAME!"
)
if not defined GMAIL (
  set /p "GMAIL=Your e-mail for commits (the one on your GitHub account): "
  if defined GMAIL git config --global user.email "!GMAIL!"
)
echo Commits will be signed as: !GNAME! !GMAIL!
echo.

rem ------------------------------------------------------------------ repository name and visibility
set "INREPO="
set /p "INREPO=Repository name [%REPO%]: "
if defined INREPO set "REPO=!INREPO: =-!"
echo.
echo   1 = Private  (only you and people you invite can see it - recommended)
echo   2 = Public   (anyone can see it)
choice /c 12 /n /m "Choose 1 or 2: "
if errorlevel 2 (set "VIS=public") else (set "VIS=private")
if "%VIS%"=="public" (
  echo.
  echo NOTE: SonicDiff uses Praat through Parselmouth, which is GPL v3.
  echo A public release is therefore under GPL v3. The LICENSE file is included.
)
echo.

rem ------------------------------------------------------------------ local repository and commit
rem allow folders on USB or other drives whose owner differs from the current user
git config --global --add safe.directory "%CD:\=/%" >nul 2>&1

if not exist ".git" (
  git init >nul
  if errorlevel 1 goto :fail
)
git checkout -B main >nul 2>&1
git add -A
if errorlevel 1 goto :fail
git diff --cached --quiet
if errorlevel 1 (
  git commit -q -m "VU3INI SonicDiff v%VER%"
  if errorlevel 1 goto :fail
  echo Committed version %VER%.
) else (
  echo Nothing new to commit since the last publish.
)
git tag -f "v%VER%" >nul
echo.

rem ------------------------------------------------------------------ remote
git remote get-url origin >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%u in ('git remote get-url origin') do echo Using existing GitHub repository: %%u
  goto :push
)

where gh >nul 2>&1
if errorlevel 1 goto :manual

gh auth status >nul 2>&1
if errorlevel 1 (
  echo Sign in to GitHub in the browser window that opens...
  gh auth login --web --git-protocol https
  if errorlevel 1 goto :manual
)
gh auth setup-git >nul 2>&1
echo Creating %VIS% repository %REPO% on GitHub...
gh repo create "%REPO%" --%VIS% --description "%DESC%" --source . --remote origin
if errorlevel 1 (
  echo.
  echo Could not create it automatically (perhaps the name is already taken^).
  goto :manual
)
goto :push

:manual
echo.
echo Create an EMPTY repository on GitHub:
echo   - Name: %REPO%
echo   - Visibility: %VIS%
echo   - Do NOT add a README, .gitignore or licence (they are already here).
echo The page https://github.com/new is opening in your browser.
start "" "https://github.com/new"
echo.
set "URL="
set /p "URL=Paste the repository URL (https://github.com/<you>/%REPO%.git): "
if not defined URL goto :fail
git remote remove origin >nul 2>&1
git remote add origin "!URL!"
if errorlevel 1 goto :fail

rem ------------------------------------------------------------------ push
:push
echo.
echo Uploading... (GitHub may ask you to sign in the first time.)
git push -u origin main
if errorlevel 1 goto :pushfail
git push -f origin "v%VER%" >nul 2>&1
echo.
echo ==================================================================
echo   Done. SonicDiff %VER% is on GitHub.
for /f "delims=" %%u in ('git remote get-url origin') do echo   %%u
echo   Run this file again after future changes to publish updates.
echo ==================================================================
pause
exit /b 0

:nogit
echo Git for Windows is not installed.
echo Install it from https://git-scm.com/download/win
echo   (or run:  winget install --id Git.Git -e)
echo then run PUBLISH_TO_GITHUB.BAT again.
start "" "https://git-scm.com/download/win"
pause
exit /b 1

:pushfail
echo.
echo The upload failed. Common causes:
echo   - You were not signed in, or the sign-in window was closed.
echo   - The GitHub repository is not empty (it has a README or licence).
echo     Delete those files on GitHub, or create a new empty repository.
echo   - The URL was mistyped. Fix it with:  git remote set-url origin ^<url^>
echo Then run PUBLISH_TO_GITHUB.BAT again.
pause
exit /b 1

:fail
echo.
echo Something went wrong (see the message above). Nothing was uploaded.
pause
exit /b 1
