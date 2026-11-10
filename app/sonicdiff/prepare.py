"""Preparation: the measurement copy and the guide copy.

Measurement copy: mono, resampled to the study rate, DC removed and a 60 Hz
high-pass. Nothing else. Every measured value comes from this copy.

Guide copy: the measurement copy with spectral-gating noise reduction (or the
separated vocal stem when available). It is only used to *find* events:
pitch tracks for segmentation, onsets and section boundaries.
"""
import numpy as np
import soxr
from scipy import signal

from . import audio_io


def measurement_copy(src, dst, consts):
    a = consts["audio"]
    y, sr = audio_io.read(src, mono=True)
    y = y.astype(np.float64)
    if sr != a["sample_rate"]:
        y = soxr.resample(y, sr, a["sample_rate"], quality="VHQ")
        sr = a["sample_rate"]
    y = y - np.mean(y)
    sos = signal.butter(4, a["highpass_hz"], btype="highpass", fs=sr, output="sos")
    y = signal.sosfiltfilt(sos, y)
    audio_io.write(dst, y, sr, subtype="FLOAT")
    return {"sample_rate": sr, "duration": len(y) / sr}


def guide_copy(measure_path, dst, vocal_stem=None):
    """Noise-reduced copy for event finding. Uses the vocal stem when one exists."""
    import noisereduce as nr
    src = vocal_stem if vocal_stem else measure_path
    y, sr = audio_io.read(src, mono=True)
    y = y.astype(np.float32)
    try:
        y2 = nr.reduce_noise(y=y, sr=sr, stationary=True, prop_decrease=0.8, n_jobs=1)
    except Exception:
        y2 = y
    audio_io.write(dst, y2, sr, subtype="FLOAT")
    return {"source": "vocal stem" if vocal_stem else "measurement copy"}


def speed_correct(y, sr, times, ratios):
    """Undo slow playback-speed drift (78 rpm, tape wow).

    ratios[i] = observed_pitch / true_pitch at times[i]. The audio is
    re-timed so that the drone stays at constant pitch.
    """
    t_in = np.arange(len(y)) / sr
    ratios = np.asarray(ratios, dtype=float)
    n_out = int(len(y) * float(np.max(ratios)) * 1.02) + 1
    # playback ran fast by r, so each output sample advances the input by 1/r samples
    step = 1.0 / np.interp(np.arange(n_out) / sr / float(np.mean(ratios)), times, ratios)
    src_t = (np.cumsum(step) - step[0]) / sr
    src_t = src_t[src_t <= t_in[-1]]
    return np.interp(src_t, t_in, y).astype(np.float32)
