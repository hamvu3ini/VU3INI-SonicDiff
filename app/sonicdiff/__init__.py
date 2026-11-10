"""VU3INI SonicDiff — cross-tradition vocal acoustic comparison.

By Sasanka Boruah -VU3INI
"""
from pathlib import Path

_vfile = Path(__file__).resolve().parent / "VERSION"
VERSION = _vfile.read_text().strip() if _vfile.exists() else "0.0.0-dev"
APP_NAME = "VU3INI SonicDiff"
