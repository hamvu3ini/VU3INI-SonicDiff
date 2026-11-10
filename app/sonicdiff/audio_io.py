"""Audio reading and writing. WAV/FLAC/OGG via libsndfile; anything else via bundled FFmpeg."""
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from .paths import exe

LOSSY_EXT = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".mp2", ".amr"}


class AudioError(Exception):
    pass


def probe(path):
    """Container facts: format, codec, bitrate, channels, sample rate, duration."""
    path = Path(path)
    info = {"ext": path.suffix.lower(), "lossy": path.suffix.lower() in LOSSY_EXT}
    try:
        si = sf.info(str(path))
        info.update(sample_rate=si.samplerate, channels=si.channels, duration=si.duration,
                    format=si.format, subtype=si.subtype)
        if si.format in ("MP3", "OGG") or si.subtype in ("VORBIS", "OPUS", "MPEG_LAYER_III"):
            info["lossy"] = True
        bits = {"PCM_16": 16, "PCM_24": 24, "PCM_32": 32, "FLOAT": 32, "DOUBLE": 64, "PCM_U8": 8, "PCM_S8": 8}
        info["bit_depth"] = bits.get(si.subtype)
        if info["lossy"] and si.duration:
            info["bitrate_kbps"] = round(path.stat().st_size * 8 / si.duration / 1000)
        return info
    except Exception:
        pass
    ffprobe = exe("ffprobe")
    if not ffprobe:
        raise AudioError("This file type needs FFmpeg, which was not found.")
    try:
        out = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                             capture_output=True, timeout=60, **_noconsole())
        d = json.loads(out.stdout or b"{}")
    except Exception as e:
        raise AudioError(f"Could not read the file: {e}")
    streams = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise AudioError("The file contains no audio stream (it may be corrupt or not an audio file).")
    s = streams[0]
    info.update(sample_rate=int(s.get("sample_rate", 0) or 0), channels=int(s.get("channels", 0) or 0),
                duration=float(d.get("format", {}).get("duration", 0) or 0), format=d.get("format", {}).get("format_name"),
                subtype=s.get("codec_name"))
    br = s.get("bit_rate") or d.get("format", {}).get("bit_rate")
    if br:
        info["bitrate_kbps"] = round(int(br) / 1000)
    if s.get("codec_name") in ("mp3", "aac", "vorbis", "opus", "wmav2", "mp2", "amr_nb"):
        info["lossy"] = True
    return info


def _noconsole():
    import sys
    if sys.platform.startswith("win"):
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


def read(path, mono=False):
    """Return (float32 array [n] or [n, ch], sample_rate)."""
    path = Path(path)
    try:
        y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception:
        ff = exe("ffmpeg")
        if not ff:
            raise AudioError("This file type needs FFmpeg, which was not found.")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "decoded.wav"
            r = subprocess.run([ff, "-v", "error", "-y", "-i", str(path), "-c:a", "pcm_f32le", str(tmp)],
                               capture_output=True, timeout=1800, **_noconsole())
            if r.returncode != 0 or not tmp.exists():
                raise AudioError("Could not decode the file: " + r.stderr.decode(errors="ignore")[-300:])
            y, sr = sf.read(str(tmp), dtype="float32", always_2d=True)
    if y.size == 0:
        raise AudioError("The file contains no audio samples.")
    if mono:
        y = y.mean(axis=1)
    return y, sr


def write(path, y, sr, subtype="PCM_24"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    y = np.asarray(y, dtype=np.float32)
    sf.write(str(path), np.clip(y, -1.0, 1.0), sr, subtype=subtype)


def segment(path, start, end):
    """Read only [start, end) seconds of a WAV, mono."""
    si = sf.info(str(path))
    a = max(0, int(start * si.samplerate))
    b = min(si.frames, int(end * si.samplerate))
    y, sr = sf.read(str(path), start=a, stop=b, dtype="float32", always_2d=True)
    return y.mean(axis=1), sr
