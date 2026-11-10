"""Built-in self-test (Settings & Tests tab). Every check uses a signal whose correct answer is known."""
import json
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np

from . import VERSION, audio_io, citations, constants, measures, prepare, qc, stats, synth, tonic
from .paths import projects_dir

SR = 48000


def _f(path):
    return projects_dir() / "_selftest.json"


def last():
    try:
        return json.loads(_f(None).read_text(encoding="utf-8"))
    except Exception:
        return None


def run(progress=None):
    c = constants.defaults()
    tests = []

    def t(name, fn):
        t0 = time.time()
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e} | {traceback.format_exc(limit=2)[-300:]}"
        tests.append({"test": name, "pass": bool(ok), "detail": detail, "seconds": round(time.time() - t0, 2)})
        if progress:
            progress(len(tests) / 16, name)

    def f0_test():
        r = measures.measure_segment(synth.voice(220, 3, SR), SR, c, "vowel", "male", tonic_hz=220)
        err = 1200 * np.log2(r["f0_median_hz"] / 220)
        return abs(err) < 1, f"F0 error {err:.3f} cents (limit 1)"

    def vib_test():
        r = measures.measure_segment(synth.voice(220, 4, SR, vib_rate=5.5, vib_cents=50), SR, c, "vowel", "male", 220)
        ok = abs(r["vibrato_rate_hz"] - 5.5) < 0.2 and abs(r["vibrato_extent_cents"] - 50) < 5
        return ok, f"rate {r['vibrato_rate_hz']:.2f} Hz (5.5), extent {r['vibrato_extent_cents']:.1f} cents (50)"

    def noise_test():
        h, cp = [], []
        for nd in (40, 30, 20, 10):
            r = measures.measure_segment(synth.voice(220, 3, SR, noise_db=nd, seed=nd), SR, c, "vowel", "male", 220)
            h.append(r["hnr_db"])
            cp.append(r["cpps_db"])
        ok = all(a > b for a, b in zip(h, h[1:])) and all(a > b for a, b in zip(cp, cp[1:]))
        return ok, "HNR " + ", ".join(f"{x:.1f}" for x in h) + " dB; CPPS " + ", ".join(f"{x:.1f}" for x in cp) + \
            " dB (noise 40→10 dB SNR; both must fall)"

    def hnr_cal():
        r = measures.measure_segment(synth.voice(220, 3, SR, noise_db=20, seed=3), SR, c, "vowel", "male", 220)
        return abs(r["hnr_db"] - 20) < 2, f"HNR {r['hnr_db']:.1f} dB for a 20 dB SNR signal (limit ±2)"

    def jit_test():
        a = measures.measure_segment(synth.voice(220, 4, SR, vib_rate=5.5, vib_cents=60), SR, c, "vowel", "male", 220)
        b = measures.measure_segment(synth.voice(220, 4, SR, jitter=0.01), SR, c, "vowel", "male", 220)
        ok = a["jitter_detrended_pct"] < 0.05 and b["jitter_detrended_pct"] > 0.3
        return ok, (f"vibrato only: local {a['jitter_local_pct']:.3f} %, detrended {a['jitter_detrended_pct']:.3f} %; "
                    f"true jitter: detrended {b['jitter_detrended_pct']:.3f} %")

    def formant_test():
        r = measures.measure_segment(synth.voice(110, 3, SR, formants=((700, 80), (1220, 90), (2600, 120))), SR, c,
                                     "vowel", "male", 110)
        ok = abs(r["f1_hz"] - 700) < 120 and abs(r["f2_hz"] - 1220) < 150
        return ok, f"F1 {r['f1_hz']:.0f} Hz (700), F2 {r['f2_hz']:.0f} Hz (1220)"

    def sf_test():
        a = measures.measure_segment(synth.voice(220, 3, SR, formants=((700, 80), (1220, 90), (2900, 300))), SR, c,
                                     "vowel", "male", 220)
        b = measures.measure_segment(synth.voice(220, 3, SR, formants=((700, 80), (1220, 90))), SR, c, "vowel", "male", 220)
        return a["singers_formant_db"] > b["singers_formant_db"] + 2, \
            f"with 2.9 kHz cluster {a['singers_formant_db']:.1f} dB vs without {b['singers_formant_db']:.1f} dB"

    def tonic_test():
        errs = []
        for sa in (110.0, 138.59, 146.83, 196.0, 233.08):
            d = synth.tanpura_drone(sa, 12, SR)
            m = synth.raga_phrase(sa, SR, swaras=(0, 200, 400, 700, 900, 700, 400, 200, 0, -500, 0, 700, 0), note_dur=0.9)
            r = tonic.propose_drone(d[:len(m)] + m, SR, consts=c, voice_type="female" if sa > 200 else "male")
            errs.append(1200 * np.log2(r["hz"] / sa))
        ok = all(abs(e) < 10 for e in errs)
        return ok, "errors " + ", ".join(f"{e:.1f}" for e in errs) + " cents (limit 10, octave must be right)"

    def key_test():
        y = np.concatenate([synth.voice(f, 0.6, SR) for f in (261.63, 329.63, 392, 523.25, 392, 329.63, 261.63, 293.66,
                                                              349.23, 392, 261.63)])
        r = tonic.propose_key(y, SR, consts=c)
        return r["key"] == "C major", f"key {r['key']}, tonic {r['hz']} Hz"

    def rhythm_test():
        from . import rhythm
        with tempfile.TemporaryDirectory() as td:
            y, times = synth.click_track(90, 10, SR)
            p = Path(td) / "c.wav"
            audio_io.write(p, y, SR, "FLOAT")
            on = rhythm.onsets(p)
        r = measures.rhythm_from_onsets(on, beats=times)
        ok = abs(r["ioi_median_s"] - 60 / 90) < 0.02 and r["npvi"] < 5 and abs(r["tempo_bpm"] - 90) < 1
        return ok, f"IOI {r['ioi_median_s']:.3f} s (0.667), nPVI {r['npvi']:.1f}, tempo {r['tempo_bpm']:.1f} BPM"

    def adsr_test():
        y = synth.voice(220, 2, SR, attack=0.1, release=0.2)
        y = np.concatenate([np.zeros(SR // 2, dtype=np.float32), y, np.zeros(SR // 2, dtype=np.float32)])
        r = measures.envelope_adsr(y.astype(float), SR, c, onsets=[0.45])
        ok = 50 < r["attack_ms"] < 130 and 100 < r["release_ms"] < 260
        return ok, f"attack {r['attack_ms']:.0f} ms (80 for a 100 ms ramp, 10→90 %), release {r['release_ms']:.0f} ms (160)"

    def qc_test():
        out = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            good = np.concatenate([np.zeros(SR // 2), synth.voice(220, 4, SR) * 0.8, np.zeros(SR // 2)])
            audio_io.write(td / "good.wav", good, SR)
            clip = synth.voice(220, 3, SR) * 6
            audio_io.write(td / "clip.wav", np.clip(clip, -1, 1), SR)
            audio_io.write(td / "silent.wav", np.zeros(SR * 3), SR)
            audio_io.write(td / "low.wav", synth.voice(220, 3, 8000) * 0.5, 8000)
            (td / "corrupt.wav").write_bytes(b"RIFF\x00\x00\x00\x00WAVEjunkjunkjunk")
            exp = {"good.wav": ("pass", "flag"), "clip.wav": ("reject",), "silent.wav": ("reject",),
                   "low.wav": ("reject",), "corrupt.wav": ("reject",)}
            ok = True
            for f, want in exp.items():
                st = qc.check(td / f, c)["status"]
                out.append(f"{f}: {st}")
                ok &= st in want
        return ok, "; ".join(out)

    def drift_test():
        sa = 146.83
        y = synth.tanpura_drone(sa, 60, SR)
        n = len(y)
        r = 1 + 0.02 * np.linspace(0, 1, n)  # pitch rises 2 % (34 cents) over a minute
        src_t = np.cumsum(r) / SR
        src_t = src_t[src_t < n / SR]
        yd = np.interp(src_t, np.arange(n) / SR, y).astype(np.float32)
        tt, ratios = tonic.drift(yd, SR, sa)
        y2 = prepare.speed_correct(yd, SR, tt, ratios)
        _, r2 = tonic.drift(y2, SR, sa)
        before = 1200 * np.log2(ratios.max() / ratios.min())
        after = 1200 * np.log2(r2.max() / r2.min())
        return after < before / 3, f"drone pitch spread {before:.1f} cents before, {after:.1f} after correction"

    def stats_test():
        rng = np.random.default_rng(0)
        import pandas as pd
        rows = []
        for g, mu, n in (("A", 0, 10), ("B", 1.2, 10)):
            for k in range(n):
                sm = rng.normal(mu, 1)
                for _ in range(4):
                    rows.append({"group": g, "singer": f"{g}{k}", "feature": "hnr_db", "value": sm + rng.normal(0, 0.3)})
        r = stats.compare(pd.DataFrame(rows))
        lv = [stats.level_for(n) for n in (1, 2, 3, 7, 8, 20)]
        ok = r["level"] == "inferential" and r["tests"][0]["p"] < 0.05 and lv == [
            "case study", "case study", "exploratory", "exploratory", "inferential", "inferential"]
        g = [x for x in r["pairwise"] if x["feature"] == "hnr_db"][0]["hedges_g"]
        return ok, f"level {r['level']}, p = {r['tests'][0]['p']:.4f}, g = {g:.2f}; levels by singer count {lv}"

    def cite_test():
        ok = all(len(citations.reference_list(s)) == len(citations.REFS) for s in citations.STYLES)
        ok &= citations.bibtex().count("@") == len(citations.REFS)
        return ok, f"{len(citations.REFS)} references in {', '.join(citations.STYLES)} and BibTeX"

    def unicode_test():
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "বৰগীত পৰীক্ষা ১.wav"
            audio_io.write(p, synth.voice(220, 2, SR), SR)
            y, sr = audio_io.read(p)
            return len(y) == 2 * SR, f"read {p.name}"

    for name, fn in [("F0 accuracy", f0_test), ("Vibrato rate and extent", vib_test), ("HNR calibration", hnr_cal),
                     ("HNR and CPPS fall with noise", noise_test), ("Jitter: vibrato removed", jit_test),
                     ("Formants F1/F2", formant_test), ("Singer's formant", sf_test), ("Tonic (drone)", tonic_test),
                     ("Key (Western)", key_test), ("Onsets, IOI, nPVI, tempo", rhythm_test), ("Envelope (ADSR)", adsr_test),
                     ("Import QC on error files", qc_test), ("Archival speed-drift correction", drift_test),
                     ("Statistics level and tests", stats_test), ("Citations", cite_test),
                     ("Assamese file names", unicode_test)]:
        t(name, fn)
    res = {"version": VERSION, "time": time.time(), "passed": sum(x["pass"] for x in tests), "total": len(tests),
           "tests": tests}
    try:
        _f(None).write_text(json.dumps(res, indent=2), encoding="utf-8")
    except Exception:
        pass
    return res


if __name__ == "__main__":
    r = run(lambda f, m: print(f"{f * 100:5.1f}%  {m}", flush=True))
    for x in r["tests"]:
        print("PASS" if x["pass"] else "FAIL", x["test"], "-", x["detail"])
    print(f"{r['passed']}/{r['total']} passed")
