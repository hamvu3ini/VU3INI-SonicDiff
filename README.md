# VU3INI SonicDiff

Cross-tradition vocal acoustic comparison of Assamese **Borgeet** and **Bhaona** songs, **Hindustani raga** and **Western opera**, from raw recordings to a thesis-ready report.

Developed in-house by **Sasanka Boruah, Senior Manager (IT), RGU**, for the **Dr. Bhupen Hazarika Centre for Creativity**.

## What it does

SonicDiff measures pitch relative to each singer's own Sa, vibrato and ornaments (gamak, andolan), loudness, formants and the singer's formant, spectral brightness, voice quality (HNR, CPPS, jitter, shimmer), note envelopes and rhythm. It compares groups with the singer as the unit of analysis, and writes a Word/PDF report with 300 dpi figures, Excel/CSV/LaTeX tables, BibTeX references (IEEE, ACS, AIP, APA 7, MLA 9) and a reproducibility record.

Every value is measured on an untouched copy of the audio; AI tools are only used to find notes, segments and beats.

## Workflow

Project → Import & QC → Prepare → Tonic → Segment & Annotate → Rhythm → Analyse → Compare → Report

## Running it

This repository holds the source code. The ready-to-run Windows 11 package (`VU3INI_SonicDiff_vX.Y.Z.zip`) also contains the Python runtime, all libraries and FFmpeg, which are not stored here. Extract it and run `SonicDiff.exe`.

To run from source with Python 3.11:

```
pip install -r requirements-lock.txt
python app/run.py --browser
```

## Licence

SonicDiff uses Praat through Parselmouth (GPL v3), so SonicDiff is distributed under the **GNU General Public License v3** (see `LICENSE`). Third-party licences are in `LICENSES/`.

By Sasanka Boruah -VU3INI
