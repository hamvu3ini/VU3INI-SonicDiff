"""Onsets and beat proposals (Phase 4).

Onsets come from the percussion stem when the recording has been separated,
otherwise from the guide copy. Beats are *proposed* (Beat This! when the AI
pack is installed, librosa otherwise) and are never used for results until
the researcher has confirmed or tapped the tala/bar cycles.
"""
import numpy as np

from . import audio_io


def onsets(path, start=None, end=None, hop_s=0.01):
    import librosa
    if start is not None:
        y, sr = audio_io.segment(path, start, end)
    else:
        y, sr = audio_io.read(path, mono=True)
    hop = int(hop_s * sr)
    env = librosa.onset.onset_strength(y=y.astype(np.float32), sr=sr, hop_length=hop)
    on = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=hop, units="time", backtrack=False)
    off = start or 0.0
    return [float(x + off) for x in on]


def propose_beats(path, start=None, end=None):
    """Return {'beats': [...], 'downbeats': [...], 'method': ...}."""
    try:
        from beat_this.inference import File2Beats  # optional AI pack
        f2b = File2Beats(checkpoint_path="final0", device="cuda" if _cuda() else "cpu", dbn=False)
        beats, downs = f2b(str(path))
        beats, downs = np.asarray(beats), np.asarray(downs)
        if start is not None:
            m = (beats >= start) & (beats <= end)
            md = (downs >= start) & (downs <= end)
            beats, downs = beats[m], downs[md]
        return {"beats": beats.tolist(), "downbeats": downs.tolist(), "method": "Beat This!"}
    except Exception:
        pass
    import librosa
    if start is not None:
        y, sr = audio_io.segment(path, start, end)
    else:
        y, sr = audio_io.read(path, mono=True)
    _, b = librosa.beat.beat_track(y=y.astype(np.float32), sr=sr, hop_length=512, units="time")
    off = start or 0.0
    return {"beats": [float(x + off) for x in np.atleast_1d(b)], "downbeats": [], "method": "librosa beat tracker"}


def _cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def tempo_curve(cycles, beats_per_cycle=None):
    """Tempo per cycle (BPM if beats_per_cycle is given, otherwise cycles per minute)."""
    c = np.sort(np.asarray(cycles, dtype=float))
    if len(c) < 2:
        return []
    d = np.diff(c)
    k = beats_per_cycle or 1
    return [{"t": float(a), "bpm": float(60 * k / x)} for a, x in zip(c[:-1], d) if x > 0]
