"""Locations inside the portable app folder. Every path is relative to it."""
import os
import shutil
import sys
from pathlib import Path

# app/sonicdiff/paths.py -> app/ -> root
APP_DIR = Path(__file__).resolve().parent.parent
ROOT = APP_DIR.parent
UI_DIR = APP_DIR / "ui"
ASSETS = UI_DIR / "assets"
BIN = ROOT / "bin"
MODELS = ROOT / "models"
DEMO = ROOT / "demo"
SETTINGS_FILE = ROOT / "settings.json"


def projects_dir():
    p = Path(os.environ.get("SONICDIFF_PROJECTS", ROOT / "projects"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def exe(name):
    """Find a bundled tool (ffmpeg, sox), falling back to PATH."""
    suffix = ".exe" if sys.platform.startswith("win") else ""
    cand = BIN / (name + suffix)
    if cand.exists():
        return str(cand)
    return shutil.which(name)
