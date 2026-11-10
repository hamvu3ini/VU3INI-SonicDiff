"""Vibrato versus ornament (gamak, andolan, kampan) classification (Phase 4).

Every pitch oscillation on a held or slowly moving note is described by its
rate, extent and regularity. Regular oscillations at 4.5-7.5 Hz with
extent under ~120 cents are labelled vibrato; slow (andolan-like) or very
wide (gamak-like) or irregular ones are labelled ornament; anything near a
boundary is 'review' and goes to the researcher's queue.
"""
import numpy as np
from scipy import signal

from . import measures


def oscillations(t, c, win_s=0.8, hop_s=0.2):
    """Slide a window along the pitch contour (cents) and describe its oscillation."""
    dt = t[1] - t[0] if len(t) > 1 else 0.01
    w = int(win_s / dt)
    h = max(1, int(hop_s / dt))
    out = []
    for a in range(0, max(0, len(c) - w), h):
        seg = c[a:a + w]
        if np.isnan(seg).mean() > 0.1:
            continue
        seg = np.where(np.isnan(seg), np.nanmedian(seg), seg)
        trend = np.polyval(np.polyfit(np.arange(w), seg, 1), np.arange(w))
        r = seg - trend
        if np.ptp(r) < 15:
            continue
        r = r - r.mean()
        ac = np.correlate(r, r, "full")[w - 1:]
        ac /= ac[0] + 1e-12
        lo, hi = int(1 / 12 / dt), min(w - 1, int(1 / 1.5 / dt))
        if hi <= lo + 1:
            continue
        lag = lo + int(np.argmax(ac[lo:hi]))
        out.append({"start": float(t[a]), "end": float(t[min(a + w, len(t) - 1)]),
                    "rate_hz": float(1 / (lag * dt)), "extent_cents": float(np.ptp(r) / 2),
                    "regularity": float(ac[lag])})
    return _merge(out)


def _merge(osc):
    """Merge overlapping windows with similar descriptions into events."""
    ev = []
    for o in osc:
        if ev and o["start"] <= ev[-1]["end"] and abs(o["rate_hz"] - ev[-1]["rate_hz"]) < 1.5:
            e = ev[-1]
            n = e.setdefault("_n", 1)
            for k in ("rate_hz", "extent_cents", "regularity"):
                e[k] = (e[k] * n + o[k]) / (n + 1)
            e["_n"] = n + 1
            e["end"] = o["end"]
        else:
            ev.append(dict(o))
    for e in ev:
        e.pop("_n", None)
        e["auto_label"] = classify(e)
    return ev


def classify(e):
    r, x, g = e["rate_hz"], e["extent_cents"], e["regularity"]
    if 4.5 <= r <= 7.5 and x <= 120 and g >= 0.5:
        return "vibrato"
    if (r < 3.5 or x > 160 or g < 0.25):
        return "ornament"
    return "review"


def analyse(y, sr, consts, voice_type="", tonic_hz=None):
    t, f0 = measures.pitch_track(y, sr, consts, voice_type)
    ref = tonic_hz or (np.median(f0[f0 > 0]) if (f0 > 0).any() else 100.0)
    c = measures.cents(f0, ref)
    return oscillations(t, c)
