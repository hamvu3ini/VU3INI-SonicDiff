"""Acoustic measures for one segment (Phase 2).

All values are computed on the measurement copy (or, when the researcher
chooses it for an accompanied recording, the separated vocal stem; its
separation bias is then reported beside each value).

Feature names are stable: they are the keys stored in the database and the
column names in exported tables.
"""
import math
import warnings

import numpy as np
import parselmouth
from parselmouth.praat import call
from scipy import signal

from . import constants as C

warnings.filterwarnings("ignore", category=RuntimeWarning)

UNITS = {}
GROUPS = {}


def _reg(name, unit, group, label):
    UNITS[name] = unit
    GROUPS[name] = (group, label)


for _n, _u, _g, _l in [
    ("f0_median_hz", "Hz", "Pitch", "Median F0"),
    ("f0_p05_hz", "Hz", "Pitch", "F0 5th percentile"),
    ("f0_p95_hz", "Hz", "Pitch", "F0 95th percentile"),
    ("range_semitones", "st", "Pitch", "Pitch range (5–95 %)"),
    ("f0_median_cents", "cents", "Pitch", "Median pitch relative to tonic"),
    ("intonation_dev_cents", "cents", "Pitch", "Mean deviation from nearest scale step"),
    ("in_tune_ratio", "ratio", "Pitch", "Share of stable frames within the accuracy band"),
    ("voiced_ratio", "ratio", "Pitch", "Voiced share of segment"),
    ("glide_rate_cents_s", "cents/s", "Pitch", "Median absolute pitch velocity (glides, meend)"),
    ("vibrato_rate_hz", "Hz", "Vibrato", "Vibrato rate"),
    ("vibrato_extent_cents", "cents", "Vibrato", "Vibrato extent (±)"),
    ("vibrato_regularity", "ratio", "Vibrato", "Vibrato regularity (autocorrelation)"),
    ("vibrato_share", "ratio", "Vibrato", "Share of held notes with regular vibrato"),
    ("intensity_mean_db", "dB", "Loudness", "Mean intensity (relative)"),
    ("dynamic_range_db", "dB", "Loudness", "Dynamic range (5–95 %)"),
    ("lufs", "LUFS", "Loudness", "Integrated loudness"),
    ("crest_factor_db", "dB", "Loudness", "Crest factor"),
    ("spectral_centroid_hz", "Hz", "Timbre", "Spectral centroid"),
    ("spectral_tilt_db_oct", "dB/oct", "Timbre", "Spectral tilt"),
    ("singers_formant_db", "dB", "Timbre", "Singer's formant energy (2–4 kHz re 0–2 kHz)"),
    ("alpha_ratio_db", "dB", "Timbre", "Alpha ratio (1–5 kHz re 50 Hz–1 kHz)"),
    ("f1_hz", "Hz", "Formants", "F1"), ("f2_hz", "Hz", "Formants", "F2"),
    ("f3_hz", "Hz", "Formants", "F3"), ("f4_hz", "Hz", "Formants", "F4"),
    ("hnr_db", "dB", "Voice quality", "Harmonics-to-noise ratio"),
    ("cpps_db", "dB", "Voice quality", "Smoothed cepstral peak prominence"),
    ("jitter_local_pct", "%", "Voice quality", "Jitter (local, Praat)"),
    ("jitter_detrended_pct", "%", "Voice quality", "Jitter after vibrato trend removed"),
    ("shimmer_local_pct", "%", "Voice quality", "Shimmer (local)"),
    ("shimmer_db", "dB", "Voice quality", "Shimmer (local, dB)"),
    ("h1_h2_db", "dB", "Harmonics", "H1–H2"),
    ("h1_h4_db", "dB", "Harmonics", "H1–H4"),
    ("harmonic_slope_db", "dB/harmonic", "Harmonics", "Harmonic amplitude slope (H1–H10)"),
    ("inharmonicity_cents", "cents", "Harmonics", "Mean partial deviation from k·F0"),
    ("attack_ms", "ms", "Envelope", "Attack time (10→90 %)"),
    ("release_ms", "ms", "Envelope", "Release time (90→10 %)"),
    ("sustain_db", "dB", "Envelope", "Sustain level re note peak"),
    ("note_rate_per_s", "notes/s", "Rhythm", "Onset rate"),
    ("ioi_median_s", "s", "Rhythm", "Median inter-onset interval"),
    ("ioi_cv", "ratio", "Rhythm", "Inter-onset interval CV"),
    ("npvi", "index", "Rhythm", "nPVI"),
    ("tempo_bpm", "BPM", "Rhythm", "Tempo"),
    ("tempo_drift_pct", "%", "Rhythm", "Tempo change first→last cycle"),
    ("syncopation_index", "ratio", "Rhythm", "Off-beat onset share"),
]:
    _reg(_n, _u, _g, _l)

for _i in range(1, 14):
    _reg(f"mfcc_{_i}", "", "MFCC", f"MFCC {_i}")
for _k in range(2, 11):
    _reg(f"h{_k}_re_h1_db", "dB", "Harmonics", f"H{_k} re H1")


# ---------------------------------------------------------------- helpers
def _snd(y, sr):
    return parselmouth.Sound(np.asarray(y, dtype=np.float64), sampling_frequency=sr)


def _nanmed(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.median(x)) if x.size else None


def pitch_track(y, sr, consts, voice_type=""):
    """Praat autocorrelation pitch at the study time step. Returns (t, f0) with 0 for unvoiced."""
    lo, hi = C.pitch_range(consts, voice_type)
    p = _snd(y, sr).to_pitch_ac(time_step=consts["pitch"]["time_step_s"], pitch_floor=lo, pitch_ceiling=hi)
    return p.xs(), p.selected_array["frequency"]


def cents(f, ref):
    f = np.asarray(f, dtype=float)
    out = np.full_like(f, np.nan)
    m = f > 0
    out[m] = 1200 * np.log2(f[m] / ref)
    return out


def stable_notes(t, c, min_dur, max_spread=80.0):
    """Find held notes: runs where pitch (cents) stays within a band around its running median."""
    dt = t[1] - t[0] if len(t) > 1 else 0.01
    win = max(3, int(round(0.15 / dt)) | 1)
    notes, start = [], None
    valid = np.isfinite(c)
    sm = np.copy(c)
    if valid.sum() > win:
        filled = np.where(valid, c, np.interp(np.arange(len(c)), np.where(valid)[0], c[valid]))
        sm = signal.medfilt(filled, win)
        sm[~valid] = np.nan
    i = 0
    n = len(c)
    while i < n:
        if not np.isfinite(sm[i]):
            i += 1
            continue
        j = i
        ref = sm[i]
        while j + 1 < n and np.isfinite(sm[j + 1]) and abs(sm[j + 1] - ref) < max_spread:
            j += 1
            ref = 0.9 * ref + 0.1 * sm[j]
        if (j - i + 1) * dt >= min_dur:
            notes.append((i, j + 1))
        i = j + 1
    return notes


def vibrato(t, c, consts):
    """Vibrato rate, extent and regularity over held notes."""
    v = consts["vibrato"]
    dt = t[1] - t[0] if len(t) > 1 else 0.01
    rates, extents, regs = [], [], []
    notes = stable_notes(t, c, v["min_note_s"], max_spread=150.0)
    for a, b in notes:
        seg = c[a:b]
        if np.isnan(seg).any() or len(seg) < int(0.5 / dt):
            continue
        k = max(5, int(round(0.4 / dt)) | 1)
        if len(seg) <= k:
            continue
        trend = signal.savgol_filter(seg, k, 2)
        r = seg - trend
        r = r[k // 2: len(r) - k // 2] if len(r) > k else r
        if len(r) < int(0.3 / dt):
            continue
        r = r - r.mean()
        ac = np.correlate(r, r, "full")[len(r) - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        lag_lo = int(1 / v["rate_max_hz"] / dt)
        lag_hi = min(len(ac) - 1, int(1 / v["rate_min_hz"] / dt))
        if lag_hi <= lag_lo + 1:
            continue
        seg_ac = ac[lag_lo:lag_hi + 1]
        li = int(np.argmax(seg_ac))
        lag = lag_lo + li
        # parabolic refinement
        if 0 < lag < len(ac) - 1:
            y0, y1, y2 = ac[lag - 1], ac[lag], ac[lag + 1]
            den = (y0 - 2 * y1 + y2)
            off = 0.5 * (y0 - y2) / den if den != 0 else 0
        else:
            off = 0
        rate = 1 / ((lag + off) * dt)
        regs.append(float(ac[lag]))
        rates.append(rate)
        # extent: least-squares sinusoid at the detected rate plus a quadratic trend, on the raw note
        tt = np.arange(len(seg)) * dt
        X = np.column_stack([np.ones_like(tt), tt, tt ** 2, np.sin(2 * np.pi * rate * tt), np.cos(2 * np.pi * rate * tt)])
        coef, *_ = np.linalg.lstsq(X, seg, rcond=None)
        extents.append(float(np.hypot(coef[3], coef[4])))
    if not rates:
        return {}
    regs = np.array(regs)
    good = regs > 0.3
    out = {"vibrato_regularity": float(np.median(regs)), "vibrato_share": float(np.mean(good))}
    if good.any():
        out["vibrato_rate_hz"] = float(np.median(np.array(rates)[good]))
        out["vibrato_extent_cents"] = float(np.median(np.array(extents)[good]))
    return out


def ltas(y, sr, bw=100.0):
    nper = int(sr / bw)
    f, p = signal.welch(y, sr, nperseg=nper, noverlap=nper // 2, window="hann")
    return f, p


def _band_db(f, p, lo, hi):
    m = (f >= lo) & (f < hi)
    return 10 * np.log10(np.sum(p[m]) + 1e-20)


def harmonics(y, sr, f0):
    """Amplitudes (dB) of harmonics 1..10 and their frequency deviation (cents) from k·F0."""
    n = len(y)
    if n < sr * 0.1 or not f0 or f0 <= 0:
        return None
    nfft = int(2 ** math.ceil(math.log2(max(n, sr // 2))))
    spec = np.abs(np.fft.rfft(y * np.hanning(n), nfft))
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    amps, devs = [], []
    for k in range(1, 11):
        target = k * f0
        if target > sr / 2 - f0:
            break
        m = (freqs > target - 0.25 * f0) & (freqs < target + 0.25 * f0)
        if not m.any():
            break
        idx = np.where(m)[0][np.argmax(spec[m])]
        amps.append(20 * np.log10(spec[idx] + 1e-20))
        if k >= 2:
            devs.append(1200 * np.log2(freqs[idx] / target))
    return np.array(amps), np.array(devs)


def envelope_adsr(y, sr, consts, onsets=None):
    """Median attack, release and sustain over the notes in a segment."""
    e = consts["envelope"]
    hop = int(0.005 * sr)
    win = int(0.01 * sr)
    if len(y) < win * 4:
        return {}
    frames = np.lib.stride_tricks.sliding_window_view(y, win)[::hop]
    env = np.sqrt(np.mean(frames ** 2, axis=1))
    tt = np.arange(len(env)) * hop / sr
    if onsets is None or len(onsets) < 1:
        import librosa
        onsets = librosa.onset.onset_detect(y=y.astype(np.float32), sr=sr, hop_length=480, units="time", backtrack=True)
    bounds = list(onsets) + [len(y) / sr]
    att, rel, sus = [], [], []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a < 0.08:
            continue
        m = (tt >= a) & (tt < b)
        seg = env[m]
        if len(seg) < 8:
            continue
        pk = int(np.argmax(seg))
        peak = seg[pk]
        if peak <= 0:
            continue
        rise = seg[: pk + 1]
        lo_i = np.where(rise <= e["attack_lo"] * peak)[0]
        hi_i = np.where(rise >= e["attack_hi"] * peak)[0]
        if hi_i.size:
            first_hi = hi_i[0]
            before = lo_i[lo_i < first_hi]
            start = before[-1] if before.size else 0
            att.append((first_hi - start) * hop / sr * 1000)
        fall = seg[pk:]
        above = np.where(fall >= e["attack_hi"] * peak)[0]
        below = np.where(fall <= e["attack_lo"] * peak)[0]
        if above.size and below.size and below[-1] > above[-1]:
            first_below = below[below > above[-1]][0]
            rel.append((first_below - above[-1]) * hop / sr * 1000)
        if len(fall) > 4:
            sus.append(20 * np.log10(np.median(fall[len(fall) // 4: 3 * len(fall) // 4]) / peak + 1e-12))
    out = {}
    if att:
        out["attack_ms"] = float(np.median(att))
    if rel:
        out["release_ms"] = float(np.median(rel))
    if sus:
        out["sustain_db"] = float(np.median(sus))
    return out


def rhythm_from_onsets(onsets, cycles=None, beats=None):
    out = {}
    on = np.sort(np.asarray(onsets, dtype=float))
    if len(on) >= 3:
        ioi = np.diff(on)
        ioi = ioi[ioi > 0.03]
        if len(ioi) >= 2:
            out["ioi_median_s"] = float(np.median(ioi))
            out["ioi_cv"] = float(np.std(ioi) / np.mean(ioi))
            pv = [abs(a - b) / ((a + b) / 2) for a, b in zip(ioi[:-1], ioi[1:])]
            out["npvi"] = float(100 * np.mean(pv))
        span = on[-1] - on[0]
        if span > 0:
            out["note_rate_per_s"] = float((len(on) - 1) / span)
    if cycles is not None and len(cycles) >= 2:
        cyc = np.sort(np.asarray(cycles, dtype=float))
        d = np.diff(cyc)
        out["tempo_drift_pct"] = float((d[0] - d[-1]) / d[0] * 100) if d[0] > 0 else None
    if beats is not None and len(beats) >= 2:
        b = np.sort(np.asarray(beats, dtype=float))
        bd = np.diff(b)
        out["tempo_bpm"] = float(60 / np.median(bd))
        if len(on) >= 2:
            # an onset is off-beat if it lies away from every beat and half-beat by > 15 % of the beat period
            per = np.median(bd)
            grid = np.sort(np.concatenate([b, b[:-1] + bd / 2]))
            dist = np.min(np.abs(on[:, None] - grid[None, :]), axis=1)
            inside = (on >= b[0]) & (on <= b[-1])
            if inside.any():
                out["syncopation_index"] = float(np.mean(dist[inside] > 0.15 * per))
    return out


# ---------------------------------------------------------------- main entry
def measure_segment(y, sr, consts, kind="phrase", voice_type="", tonic_hz=None,
                    onsets=None, cycles=None, beats=None):
    """Compute every feature that applies to this segment kind. Returns {feature: value}."""
    y = np.asarray(y, dtype=np.float64)
    out = {}
    if len(y) < int(0.2 * sr) or np.max(np.abs(y)) < 1e-6:
        return out
    snd = _snd(y, sr)

    if kind == "vowel":
        # analyse the steady core only
        cf = consts["segments"]["vowel_core_fraction"]
        cut = int(len(y) * (1 - cf) / 2)
        if cut:
            y = y[cut: len(y) - cut]
            snd = _snd(y, sr)

    # ---------- pitch (all kinds except pure rhythm) ----------
    t, f0 = pitch_track(y, sr, consts, voice_type)
    voiced = f0 > 0
    out["voiced_ratio"] = float(np.mean(voiced)) if len(f0) else 0.0
    if voiced.sum() >= 5 and kind != "rhythm":
        fv = f0[voiced]
        out["f0_median_hz"] = float(np.median(fv))
        out["f0_p05_hz"] = float(np.percentile(fv, 5))
        out["f0_p95_hz"] = float(np.percentile(fv, 95))
        out["range_semitones"] = float(12 * np.log2(out["f0_p95_hz"] / out["f0_p05_hz"]))
        if tonic_hz:
            c = cents(f0, tonic_hz)
            out["f0_median_cents"] = float(np.nanmedian(c))
            notes = stable_notes(t, c, 0.12)
            if notes:
                devs = []
                for a, b in notes:
                    m = float(np.nanmedian(c[a:b]))
                    devs.append(m - 100 * round(m / 100))
                devs = np.array(devs)
                out["intonation_dev_cents"] = float(np.mean(np.abs(devs)))
                out["in_tune_ratio"] = float(np.mean(np.abs(devs) <= consts["pitch"]["accuracy_band_cents"]))
        else:
            c = cents(f0, np.median(fv))
        cv = np.where(np.isfinite(c), c, np.nan)
        vel = np.abs(np.diff(cv)) / (t[1] - t[0]) if len(t) > 1 else np.array([])
        vel = vel[np.isfinite(vel)]
        if vel.size:
            out["glide_rate_cents_s"] = float(np.median(vel))
        out.update(vibrato(t, c, consts))

    # ---------- loudness ----------
    L = consts["loudness"]
    win = int(L["window_s"] * sr)
    hop = int(L["hop_s"] * sr)
    if len(y) > win:
        fr = np.lib.stride_tricks.sliding_window_view(y, win)[::hop]
        rms = np.sqrt(np.mean(fr ** 2, axis=1))
        db = 20 * np.log10(rms + 1e-12)
        act = db > (db.max() - 50)
        out["intensity_mean_db"] = float(10 * np.log10(np.mean(rms[act] ** 2) + 1e-20))
        out["dynamic_range_db"] = float(np.percentile(db[act], 95) - np.percentile(db[act], 5))
        out["crest_factor_db"] = float(20 * np.log10(np.max(np.abs(y)) / (np.sqrt(np.mean(y ** 2)) + 1e-12)))
    if len(y) >= 0.5 * sr:
        try:
            import pyloudnorm
            v = pyloudnorm.Meter(sr).integrated_loudness(y)
            if np.isfinite(v):
                out["lufs"] = float(v)
        except Exception:
            pass

    # ---------- timbre: normalised copy so level does not shift spectral values ----------
    if kind != "rhythm":
        f, p = ltas(y, sr, consts["spectral"]["ltas_bandwidth_hz"])
        tot = np.sum(p[(f >= 50) & (f < 8000)]) + 1e-20
        out["spectral_centroid_hz"] = float(np.sum(f[(f >= 50) & (f < 8000)] * p[(f >= 50) & (f < 8000)]) / tot)
        out["singers_formant_db"] = float(_band_db(f, p, 2000, 4000) - _band_db(f, p, 0, 2000))
        out["alpha_ratio_db"] = float(_band_db(f, p, 1000, 5000) - _band_db(f, p, 50, 1000))
        m = (f >= 100) & (f <= 5000)
        if m.sum() > 5:
            slope = np.polyfit(np.log2(f[m]), 10 * np.log10(p[m] + 1e-20), 1)[0]
            out["spectral_tilt_db_oct"] = float(slope)
        try:
            import librosa
            S = consts["spectral"]
            mf = librosa.feature.mfcc(y=y.astype(np.float32), sr=sr, n_mfcc=S["n_mfcc"], n_mels=S["n_mels"],
                                      n_fft=S["n_fft"], hop_length=S["hop"])
            for i in range(mf.shape[0]):
                out[f"mfcc_{i + 1}"] = float(np.mean(mf[i]))
        except Exception:
            pass
        # formants over voiced frames
        F = consts["formant"]
        try:
            fm = snd.to_formant_burg(time_step=0.01, max_number_of_formants=F["n_formants"],
                                     maximum_formant=C.max_formant(consts, voice_type),
                                     window_length=F["window_s"], pre_emphasis_from=50.0)
            ts = fm.xs()
            vt = set(np.round(t[voiced], 2))
            for k in (1, 2, 3, 4):
                vals = [fm.get_value_at_time(k, x) for x in ts if round(x, 2) in vt]
                v = _nanmed(vals)
                if v:
                    out[f"f{k}_hz"] = v
        except Exception:
            pass

    # ---------- voice quality and harmonics: held vowels only ----------
    if kind == "vowel" and voiced.sum() >= 10:
        lo, hi = C.pitch_range(consts, voice_type)
        H = consts["hnr"]
        try:
            hn = snd.to_harmonicity_cc(time_step=H["time_step_s"], minimum_pitch=max(H["min_pitch_hz"], lo),
                                      silence_threshold=H["silence_threshold"], periods_per_window=H["periods_per_window"])
            v = hn.values[0]
            v = v[v > -200]
            if v.size:
                out["hnr_db"] = float(np.mean(v))
        except Exception:
            pass
        # CPPS: peak search range follows this segment's own F0
        fmed = float(np.median(f0[voiced]))
        plo = max(lo, fmed / 1.5)
        phi = min(hi * 1.2, fmed * 1.5)
        cp = consts["cpps"]
        try:
            pc = call(snd, "To PowerCepstrogram", plo, cp["time_step_s"], cp["max_frequency_hz"], cp["pre_emphasis_hz"])
            v = call(pc, "Get CPPS", "yes", cp["time_smoothing_s"], cp["quefrency_smoothing_s"], plo, phi, 0.05,
                     "Parabolic", 0.001, 0.05, "Straight", "Robust")
            if v is not None and np.isfinite(v):
                out["cpps_db"] = float(v)
        except Exception:
            pass
        P = consts["perturbation"]
        try:
            pitch = snd.to_pitch_cc(time_step=0.005, pitch_floor=plo, pitch_ceiling=phi)
            pp = call([snd, pitch], "To PointProcess (cc)")
            j = call(pp, "Get jitter (local)", 0, 0, P["period_floor_s"], P["period_ceiling_s"], P["max_period_factor"])
            s = call([snd, pp], "Get shimmer (local)", 0, 0, P["period_floor_s"], P["period_ceiling_s"],
                     P["max_period_factor"], P["max_amplitude_factor"])
            sdb = call([snd, pp], "Get shimmer (local_dB)", 0, 0, P["period_floor_s"], P["period_ceiling_s"],
                       P["max_period_factor"], P["max_amplitude_factor"])
            if np.isfinite(j):
                out["jitter_local_pct"] = float(j * 100)
            if np.isfinite(s):
                out["shimmer_local_pct"] = float(s * 100)
            if np.isfinite(sdb):
                out["shimmer_db"] = float(sdb)
            # detrended jitter: remove the slow (vibrato) movement of the period sequence first
            times = np.asarray(call(pp, "To Matrix").values).ravel()
            per = np.diff(times)
            ok = (per >= P["period_floor_s"]) & (per <= P["period_ceiling_s"])
            per = per[ok]
            if len(per) > 30:
                k = 11
                trend = signal.savgol_filter(per, k, 2)
                out["jitter_detrended_pct"] = float(np.mean(np.abs(np.diff(per - trend))) / np.mean(per) * 100)
        except Exception:
            pass
        hr = harmonics(y, sr, fmed)
        if hr is not None:
            amps, devs = hr
            if len(amps) >= 2:
                out["h1_h2_db"] = float(amps[0] - amps[1])
            if len(amps) >= 4:
                out["h1_h4_db"] = float(amps[0] - amps[3])
            for k in range(2, len(amps) + 1):
                out[f"h{k}_re_h1_db"] = float(amps[k - 1] - amps[0])
            if len(amps) >= 3:
                out["harmonic_slope_db"] = float(np.polyfit(np.arange(1, len(amps) + 1), amps, 1)[0])
            if len(devs):
                out["inharmonicity_cents"] = float(np.mean(np.abs(devs)))

    # ---------- envelope (phrases) ----------
    if kind in ("phrase", "rhythm"):
        out.update(envelope_adsr(y, sr, consts, onsets))

    # ---------- rhythm ----------
    if kind in ("rhythm", "phrase") and onsets is not None and len(onsets) >= 3:
        out.update({k: v for k, v in rhythm_from_onsets(onsets, cycles, beats).items() if v is not None})

    return {k: v for k, v in out.items() if v is not None and np.isfinite(v)}
