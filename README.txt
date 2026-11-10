VU3INI SonicDiff 0.9.3
By Sasanka Boruah -VU3INI
=====================================================================

Cross-tradition vocal acoustic comparison for PhD research: Assamese
Borgeet and Bhaona songs, Hindustani raga and Western opera.

START
  1. Extract the whole zip file (right-click > Extract All). Do not run
     it from inside the zip.
  2. Double-click SonicDiff.exe          (its own window)
     or SonicDiff-Browser.exe            (opens in your web browser)
     or Start-SonicDiff-Browser.bat      (browser, with a console window)
  3. Optional: Install.bat copies SonicDiff to C:\VU3INI\SonicDiff and
     adds Desktop / Start-menu shortcuts.

  No Python, no administrator rights and no internet are needed. Your
  studies are saved in the "projects" folder next to SonicDiff.exe.

FIRST STEPS
  Settings & Tests > Run self-test       (checks every measure; ~1 minute)
  Project > Load demo study              (synthetic data to try every tab)

WORKFLOW (the numbered tabs)
  1 Project      study, comparison groups, singer IDs, constants
  2 Import & QC  add recordings + metadata; automatic quality control
  3 Prepare      measurement copy, guide copy, optional voice separation
  4 Tonic        propose, listen against the reference drone, confirm
  5 Segment      phrases, held vowels, rhythm spans, singer labels,
                 vibrato/ornament review, musicological notes
  6 Rhythm       proposed beats; tap tala/bar cycles with the Space bar
  7 Analyse      all measures with locked constants
  8 Compare      statistics level by singer count, effect sizes, tests
  9 Report       Word, PDF, Excel, CSV, LaTeX, BibTeX, 300 dpi figures

VOICE SEPARATION AND THE RTX 5060 (optional AI pack)
  The core app works without it. For separating the voice from tanpura,
  khol, tabla or orchestra, run Install-AI-Pack.bat once. It installs
  PyTorch 2.7 for CUDA 12.8 (needed by RTX 50-series cards), the
  audio-separator BS-RoFormer model and Beat This!. It downloads about
  3-4 GB once, or installs offline from an "ai_pack" folder made with
  Make-Offline-AI-Pack.bat on any computer with internet.

THE DESKTOP WINDOW
  SonicDiff.exe uses Microsoft Edge WebView2, which Windows 11 includes.
  If the window does not open, SonicDiff opens in your browser instead.

PUBLISH TO GITHUB
  PUBLISH_TO_GITHUB.BAT uploads the source code (not the runtime,
  libraries, models or your projects) to a private or public GitHub
  repository. Needs Git for Windows; GitHub CLI (gh) is optional.

REPAIR
  Install.bat /repair   reinstalls every library from the wheels folder.
  Logs are in the "logs" folder.

LICENCES
  SonicDiff uses Praat through Parselmouth (GPL v3). Private use for a
  thesis is fine; a public release of SonicDiff must also be under the
  GPL. FFmpeg is bundled as a separate program (see LICENSES).
  All licence texts are in the LICENSES folder.

Results describe stylistic difference, not quality.
