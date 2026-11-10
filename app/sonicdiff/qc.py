"""Import quality control (Sample Constants doc, sections 1 and 6).

Each check returns pass / flag / reject with a plain-language reason. A file's
overall status is the worst of its checks. Archival-group files have their
noise and bandwidth rejections softened to flags, because they are analysed
separately and only for pitch, ornament and tempo measures.
"""
import numpy as np
import pyloudnorm
from scipy import signal

from . import audio_io

ORDER = {"pass": 0, "flag": 1, "reject": 2}


def _db(x):
    return 20 * np.log10(np.maximum(x, 1e-12))


def check(path, consts, role="study"):
    a = consts["audio"]
    checks = []

    def add(name, status, value, msg, unit=""):
        checks.append({"check": name, "status": status, "value": value, "unit": unit, "message": msg})

    try:
        info = audio_io.probe(path)
        y, sr = audio_io.read(path)
    except audio_io.AudioError as e:
        return {"status": "reject", "checks": [{"check": "decode", "status": "reject", "value": None,
                                                 "unit": "", "message": str(e)}], "info": {}}
    except Exception as e:  # corrupt files raise many kinds of errors
        return {"status": "reject", "checks": [{"check": "decode", "status": "reject", "value": None, "unit": "",
                                                 "message": f"The file could not be decoded ({type(e).__name__})."}],
                "info": {}}

    n, ch = y.shape
    dur = n / sr
    info.update(duration=dur, sample_rate=sr, channels=ch)
    mono = y.mean(axis=1)

    # decode / length
    if dur < 1.0:
        add("duration", "reject", round(dur, 2), "Shorter than 1 second; too short to analyse.", "s")
    elif dur > 7200:
        add("duration", "flag", round(dur, 1), "Longer than 2 hours; analysis will be slow. Consider trimming.", "s")
    else:
        add("duration", "pass", round(dur, 1), "Length is fine.", "s")

    # silence
    peak = float(np.max(np.abs(y)))
    peak_db = float(_db(peak))
    if peak_db < -60:
        add("silence", "reject", round(peak_db, 1), "The file is silent or almost silent.", "dBFS")
        return {"status": "reject", "checks": checks, "info": info}

    # sample rate
    if sr < 16000:
        add("sample_rate", "reject", sr, "Below 16 kHz: too band-limited for timbre and voice-quality measures.", "Hz")
    elif sr < 44100:
        add("sample_rate", "flag", sr, "Below 44.1 kHz: high-frequency measures (singer's formant) are limited.", "Hz")
    else:
        add("sample_rate", "pass", sr, f"Will be resampled to {a['sample_rate']} Hz for analysis." if sr != a["sample_rate"]
            else "Matches the study sample rate.", "Hz")

    # format
    if info.get("lossy"):
        kb = info.get("bitrate_kbps")
        if kb and kb < a["lossy_min_kbps"]:
            add("format", "reject", kb, f"Lossy source below {a['lossy_min_kbps']} kbps: harmonics and noise "
                "measures are unreliable.", "kbps")
        else:
            add("format", "flag", kb, "Lossy source: analyse in a separate stratum and say so in the thesis.", "kbps")
    else:
        bd = info.get("bit_depth")
        if bd and bd < 16:
            add("format", "flag", bd, "Bit depth below 16.", "bit")
        else:
            add("format", "pass", bd, "Uncompressed / lossless source.", "bit")

    # channels
    add("channels", "pass", ch, "Stereo will be averaged to mono." if ch > 1 else "Mono.")

    # clipping: runs of >= 3 consecutive near-full-scale samples
    clip_runs = 0
    for c in range(ch):
        hot = np.abs(y[:, c]) >= 0.999
        if hot.any():
            d = np.diff(np.concatenate(([0], hot.astype(np.int8), [0])))
            starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
            clip_runs += int(np.sum((ends - starts) >= 3))
    if clip_runs:
        add("clipping", "reject", clip_runs, "Clipped passages found; clipping adds false harmonics.", "runs")
    else:
        add("clipping", "pass", 0, "No clipping.", "runs")

    # sample peak and true peak (4x oversampled)
    seg = mono if len(mono) <= sr * 600 else mono[: sr * 600]
    tp = float(np.max(np.abs(signal.resample_poly(seg, 4, 1)))) if len(seg) > 16 else peak
    tp_db = float(_db(max(tp, peak)))
    if tp_db > a["peak_limit_dbfs"]:
        add("true_peak", "flag", round(tp_db, 2), f"True peak above {a['peak_limit_dbfs']} dBFS.", "dBTP")
    else:
        add("true_peak", "pass", round(tp_db, 2), "Peak level is within limits.", "dBTP")

    # noise floor and SNR from 50 ms frame RMS
    fl = int(0.05 * sr)
    frames = mono[: (len(mono) // fl) * fl].reshape(-1, fl) if len(mono) >= fl * 4 else mono[None, :]
    rms_db = _db(np.sqrt(np.mean(frames ** 2, axis=1)))
    level = float(np.percentile(rms_db, 95))
    gaps = rms_db[rms_db < level - 35]  # true pauses only; a soft drone is not noise
    soft = role in ("archival", "test")
    if len(gaps) < max(3, 0.02 * len(rms_db)):
        # continuous sound (drone, orchestra) with no pauses: the noise floor cannot be read from the file
        floor, snr = None, None
        add("noise_floor", "flag", None, "No quiet passages to measure the noise floor (continuous drone or "
            "accompaniment). Check by ear; voice-quality values will rely on separation or solo passages.", "dBFS")
    else:
        floor = float(np.median(gaps))
        snr = level - floor
        if floor > a["noise_floor_limit_dbfs"]:
            add("noise_floor", "flag", round(floor, 1), f"Noise floor above {a['noise_floor_limit_dbfs']} dBFS.", "dBFS")
        else:
            add("noise_floor", "pass", round(floor, 1), "Noise floor is low.", "dBFS")
        if snr < a["min_snr_db"]:
            add("snr", "flag" if soft else "reject", round(snr, 1),
                f"Signal-to-noise ratio below {a['min_snr_db']} dB.", "dB")
        else:
            add("snr", "pass", round(snr, 1), "Signal-to-noise ratio is adequate.", "dB")

    # effective bandwidth (frequency below which 99 % of energy lies above 100 Hz)
    f, pxx = signal.welch(seg, sr, nperseg=4096)
    m = f > 100
    cum = np.cumsum(pxx[m]) / max(np.sum(pxx[m]), 1e-20)
    bw = float(f[m][np.searchsorted(cum, 0.99)]) if m.any() else 0
    hf = float(10 * np.log10((np.sum(pxx[(f > 4000) & (f < 8000)]) + 1e-20) / (np.sum(pxx[(f > 300) & (f < 3000)]) + 1e-20)))
    info["bandwidth_99_hz"] = round(bw)
    if hf < -55 or sr < 16000:
        add("bandwidth", "flag" if soft else "reject", round(hf, 1),
            "Almost no energy above 4 kHz (band-limited, e.g. 78 rpm transfer): singer's formant, HNR and CPPS "
            "are not meaningful.", "dB")
    else:
        add("bandwidth", "pass", round(hf, 1), "Energy present above 4 kHz.", "dB")

    # DC offset
    dc = float(np.mean(mono))
    add("dc_offset", "flag" if abs(dc) > 0.01 else "pass", round(dc, 4),
        "DC offset present; it will be removed in the measurement copy." if abs(dc) > 0.01 else "No DC offset.")

    # loudness and crest factor (informative)
    try:
        lufs = float(pyloudnorm.Meter(sr).integrated_loudness(y if ch > 1 else mono))
    except Exception:
        lufs = float("nan")
    rms_all = float(np.sqrt(np.mean(mono ** 2)))
    info.update(lufs=None if np.isnan(lufs) else round(lufs, 1), crest_db=round(peak_db - float(_db(rms_all)), 1),
                noise_floor_dbfs=None if floor is None else round(floor, 1), snr_db=None if snr is None else round(snr, 1), true_peak_dbtp=round(tp_db, 2))

    status = max((c["status"] for c in checks), key=lambda s: ORDER[s])
    return {"status": status, "checks": checks, "info": info}


def voice_presence(path, sr_target=16000):
    """Rough share of frames that contain pitched voice-like sound (used by tests and QC hints)."""
    import parselmouth
    y, sr = audio_io.read(path, mono=True)
    snd = parselmouth.Sound(y.astype(np.float64), sampling_frequency=sr)
    p = snd.to_pitch_ac(time_step=0.02, pitch_floor=70, pitch_ceiling=1100, voicing_threshold=0.6)
    f0 = p.selected_array["frequency"]
    return float(np.mean(f0 > 0)) if f0.size else 0.0
