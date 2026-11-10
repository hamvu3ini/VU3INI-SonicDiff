"""Tonic proposal (Phase 3).

Indian music ("drone" method): combines the drone's spectral peaks with the
singer's folded pitch histogram. The tonic is the pitch class that is both a
strong drone partial and a strong, stable melody note with a strong fifth
(Pa) or fourth (Ma) above it. This follows the multi-pitch idea of Gulati et
al. (2014) in a simple, transparent form; the researcher confirms by ear.

Western music ("key" method): key centre from a chroma profile matched to
Krumhansl–Kessler key profiles, placed in the octave below the melody median.

Archival drift: the drone partial nearest the tonic is tracked over time; the
ratio to its median is the playback-speed error.
"""
import numpy as np
from scipy import signal

from . import measures

A4 = 440.0
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
REF = 55.0  # Hz, cents origin


def _pc_hist(f0, bins=120, smooth=2):
    f = f0[f0 > 0]
    if f.size < 20:
        return None
    c = 1200 * np.log2(f / REF) % 1200
    h, _ = np.histogram(c, bins=bins, range=(0, 1200))
    h = h.astype(float)
    k = np.exp(-0.5 * (np.arange(-3 * smooth, 3 * smooth + 1) / smooth) ** 2)
    h = np.convolve(np.concatenate([h[-len(k):], h, h[:len(k)]]), k / k.sum(), "same")[len(k):-len(k)]
    return h / (h.max() + 1e-12)


def _hval(h, cents_pc):
    i = int(round(cents_pc % 1200 / 10)) % len(h)
    return float(max(h[i], h[(i - 1) % len(h)], h[(i + 1) % len(h)]))


def drone_peaks(y, sr, fmin=40, fmax=1100, n=24):
    nper = min(int(sr * 4), len(y))  # 0.25 Hz resolution
    f, p = signal.welch(y, sr, nperseg=nper, noverlap=nper // 2)
    m = (f >= fmin) & (f <= fmax)
    db = 10 * np.log10(p[m] + 1e-20)
    fm = f[m]
    # salience above a smoothed floor
    floor = signal.medfilt(db, 51 if len(db) > 51 else (len(db) // 2) * 2 - 1)
    sal = db - floor
    idx, props = signal.find_peaks(sal, height=6, distance=5)
    order = np.argsort(props["peak_heights"])[::-1][:n]
    out = []
    for i in order:
        j = idx[i]
        if 0 < j < len(db) - 1:  # parabolic interpolation of the peak frequency
            a, b, c = db[j - 1], db[j], db[j + 1]
            den = a - 2 * b + c
            off = 0.5 * (a - c) / den if den else 0.0
        else:
            off = 0.0
        out.append((float(fm[j] + off * (fm[1] - fm[0])), float(props["peak_heights"][i])))
    return out


def propose_drone(y, sr, f0=None, consts=None, voice_type=""):
    if f0 is None:
        from . import constants as C
        consts = consts or C.defaults()
        _, f0 = measures.pitch_track(y, sr, consts, voice_type)
    h = _pc_hist(np.asarray(f0))
    peaks = drone_peaks(y, sr)
    if h is None and not peaks:
        return None
    cands = {}
    for fr, sal in peaks:
        pc = 1200 * np.log2(fr / REF) % 1200
        key = int(round(pc / 10)) % 120
        cands[key] = cands.get(key, 0) + min(sal, 30) / 30
    if h is not None:
        for i in signal.find_peaks(np.concatenate([[0], h, [0]]), height=0.3)[0] - 1:
            cands.setdefault(int(i) % 120, 0.0)
    top = max(cands.values()) if cands else 1.0
    cands = {k: v / top if top > 0 else 0.0 for k, v in cands.items()}
    best, best_s, scored = None, -1, []
    for key, dsal in cands.items():
        pc = key * 10
        s = 1.0 * dsal
        if h is not None:
            s += 1.0 * _hval(h, pc) + 0.6 * _hval(h, pc + 700) + 0.3 * _hval(h, pc + 500) - 0.4 * _hval(h, pc + 100)
        scored.append((s, pc))
        if s > best_s:
            best, best_s = pc, s
    if best is None:
        return None
    # refine with the exact drone partial when one lies within 20 cents of the chosen pitch class
    base_pc = best
    for fr, sal in peaks:
        d = (1200 * np.log2(fr / REF) - best + 600) % 1200 - 600
        if abs(d) <= 20:
            base_pc = (1200 * np.log2(fr / REF)) % 1200
            break
    base = REF * 2 ** (base_pc / 1200)
    # octave: the one whose middle register (Pa below Sa up to upper Sa) holds most of the melody
    fv = np.asarray(f0)[np.asarray(f0) > 0]
    if fv.size:
        best_oct, best_frac = base, -1
        for k in range(-2, 5):
            sa = base * 2 ** k
            if not 50 <= sa <= 700:
                continue
            frac = np.mean((fv >= sa * 2 ** (-7 / 12) * 0.98) & (fv < sa * 2 * 1.02))
            if frac > best_frac + 0.02:
                best_oct, best_frac = sa, frac
        base = best_oct
    else:
        while base < 100:
            base *= 2
    scored.sort(reverse=True)
    alts = []
    for s, pc in scored[1:4]:
        f = REF * 2 ** (pc / 1200)
        while f * 2 <= base * 1.5:
            f *= 2
        while f > base * 1.5:
            f /= 2
        alts.append({"hz": round(f, 2), "score": round(s, 3)})
    return {"hz": round(float(base), 2), "method": "drone+melody", "score": round(best_s, 3), "alternatives": alts}


def propose_key(y, sr, f0=None, consts=None, voice_type=""):
    import librosa
    chroma = librosa.feature.chroma_cqt(y=np.asarray(y, dtype=np.float32), sr=sr, hop_length=1024)
    prof = chroma.mean(axis=1)
    best = (-2, 0, "major")
    for i in range(12):
        for name, tpl in (("major", MAJOR), ("minor", MINOR)):
            r = np.corrcoef(prof, np.roll(tpl, i))[0, 1]
            if r > best[0]:
                best = (r, i, name)
    r, i, mode = best
    # chroma bin 0 = C; C4 = 261.63 Hz
    hz = 261.6256 * 2 ** (i / 12)
    if f0 is None:
        from . import constants as C
        consts = consts or C.defaults()
        _, f0 = measures.pitch_track(y, sr, consts, voice_type)
    fv = np.asarray(f0)[np.asarray(f0) > 0]
    if fv.size:
        med = np.median(fv)
        while hz > med:
            hz /= 2
        while hz * 2 <= med:
            hz *= 2
    return {"hz": round(float(hz), 2), "method": "key", "key": f"{NOTE_NAMES[i]} {mode}", "score": round(float(r), 3),
            "alternatives": []}


def drift(y, sr, tonic_hz, win_s=20.0):
    """Track the drone partial nearest the tonic; return (times, ratios) for speed correction."""
    n = int(win_s * sr)
    if len(y) < 2 * n:
        return None
    times, ratios = [], []
    for a in range(0, len(y) - n + 1, n // 2):
        seg = y[a:a + n]
        nper = min(len(seg), int(sr / 0.5))
        f, p = signal.welch(seg, sr, nperseg=nper)
        lo, hi = tonic_hz * 2 ** (-150 / 1200), tonic_hz * 2 ** (150 / 1200)
        m = (f >= lo) & (f <= hi)
        if not m.any():
            continue
        times.append((a + n / 2) / sr)
        ratios.append(f[m][np.argmax(p[m])] / tonic_hz)
    if len(ratios) < 2:
        return None
    ratios = np.array(ratios) / np.median(ratios)
    return np.array(times), ratios
