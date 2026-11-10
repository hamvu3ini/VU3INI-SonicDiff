"""Synthetic test signals with known answers (used by the self-test and the demo corpus)."""
import numpy as np


def voice(f0=220.0, dur=3.0, sr=48000, vib_rate=0.0, vib_cents=0.0, noise_db=None, n_harm=40,
          tilt_db_oct=-12.0, formants=((700, 80), (1220, 90), (2600, 120)), jitter=0.0, seed=0,
          amp=0.3, attack=0.05, release=0.1):
    """Harmonic voice-like tone: glottal-like spectral tilt, formant filtering, optional vibrato/noise/jitter."""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    t = np.arange(n) / sr
    cents = vib_cents * np.sin(2 * np.pi * vib_rate * t) if vib_rate else np.zeros(n)
    if jitter:
        # cycle-to-cycle F0 noise, smoothed to ~1 period
        jit = rng.normal(0, jitter, n)
        k = max(1, int(sr / f0))
        jit = np.convolve(jit, np.ones(k) / k, "same") * np.sqrt(k)
        cents = cents + 1200 * np.log2(1 + jit)
    inst = f0 * 2 ** (cents / 1200)
    phase = 2 * np.pi * np.cumsum(inst) / sr
    y = np.zeros(n)
    for k in range(1, n_harm + 1):
        fk = k * f0
        if fk > sr / 2 - 1000:
            break
        a = 10 ** (tilt_db_oct * np.log2(k) / 20)
        for fc, bw in formants:
            a *= 1 + 3.0 / (1 + ((fk - fc) / bw) ** 2)
        y += a * np.sin(k * phase)
    y = y / np.max(np.abs(y)) * amp
    env = np.ones(n)
    na, nr = int(attack * sr), int(release * sr)
    if na:
        env[:na] = np.linspace(0, 1, na)
    if nr:
        env[-nr:] = np.linspace(1, 0, nr)
    y *= env
    if noise_db is not None:
        rms = np.sqrt(np.mean(y ** 2))
        y = y + rng.normal(0, rms * 10 ** (-noise_db / 20), n)
    return y.astype(np.float32)


def tanpura_drone(sa=146.83, dur=10.0, sr=48000, amp=0.1, seed=1):
    """Pa-Sa-Sa-Sa drone with rich, slowly beating partials."""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    t = np.arange(n) / sr
    y = np.zeros(n)
    for f, w in ((sa * 1.5 / 2, 0.8), (sa, 1.0), (sa, 0.9), (sa / 2, 0.9)):
        for k in range(1, 25):
            det = 1 + rng.normal(0, 0.0004)
            y += w * (0.8 ** k) * np.sin(2 * np.pi * f * k * det * t + rng.uniform(0, 6.28))
    return (y / np.max(np.abs(y)) * amp).astype(np.float32)


def raga_phrase(sa=146.83, sr=48000, swaras=(0, 200, 400, 500, 700, 500, 400, 200, 0), note_dur=0.8,
                vib_cents=0.0, glide=0.12, seed=2):
    """A sung phrase over given swaras (cents re Sa) with meend-like glides."""
    rng = np.random.default_rng(seed)
    per = int(note_dur * sr)
    cents = []
    prev = swaras[0]
    for s in swaras:
        g = int(glide * sr)
        cents.append(np.linspace(prev, s, g))
        cents.append(np.full(per - g, s, dtype=float))
        prev = s
    c = np.concatenate(cents) + rng.normal(0, 3, 1).item()
    n = len(c)
    t = np.arange(n) / sr
    if vib_cents:
        c = c + vib_cents * np.sin(2 * np.pi * 5.5 * t)
    inst = sa * 2 ** (c / 1200)
    phase = 2 * np.pi * np.cumsum(inst) / sr
    y = sum((0.7 ** k) * np.sin(k * phase) for k in range(1, 25))
    return (y / np.max(np.abs(y)) * 0.3).astype(np.float32)


def click_track(bpm=90.0, dur=10.0, sr=48000, accel=0.0, seed=3):
    """Percussive clicks; accel = fractional tempo increase over the duration. Returns (audio, onset times)."""
    n = int(dur * sr)
    y = np.zeros(n, dtype=np.float32)
    times = []
    tt = 0.2
    while tt < dur - 0.2:
        times.append(tt)
        bpm_now = bpm * (1 + accel * tt / dur)
        tt += 60 / bpm_now
    burst = (np.random.default_rng(seed).normal(0, 1, int(0.03 * sr)) * np.exp(-np.linspace(0, 8, int(0.03 * sr)))).astype(np.float32)
    for x in times:
        i = int(x * sr)
        y[i:i + len(burst)] += burst[: max(0, min(len(burst), n - i))] * 0.5
    return y, np.array(times)
