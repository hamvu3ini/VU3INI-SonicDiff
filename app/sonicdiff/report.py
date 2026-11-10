"""Thesis report (Phase 5): figures, tables, DOCX, PDF, LaTeX, CSV/Excel, BibTeX and appendices."""
import datetime as dt
import json
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import VERSION, audio_io, citations, measures, service, stats
from .paths import ASSETS

PALETTE = ["#2563eb", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2", "#65a30d", "#dc2626"]


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 10,
                         "axes.titlelocation": "left", "figure.dpi": 100})
    return plt


def _save(fig, out, name):
    plt = _plt()
    fig.savefig(out / f"{name}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(out / f"{name}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out / f"{name}.png"


def _colors(groups):
    return {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)}


# ------------------------------------------------------------------ figures
def fig_effects(cmp, out):
    plt = _plt()
    rows = [r for r in cmp["pairwise"] if r.get("hedges_g") is not None and r.get("ci_low") is not None]
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["absg"] = df["hedges_g"].abs()
    pairs = df[["group_a", "group_b"]].drop_duplicates().values.tolist()
    keep = (df.groupby("feature")["absg"].max().sort_values(ascending=False).head(18).index.tolist())
    df = df[df.feature.isin(keep)]
    fig, ax = plt.subplots(figsize=(7.2, 0.32 * len(keep) + 1.4))
    offs = np.linspace(-0.25, 0.25, len(pairs)) if len(pairs) > 1 else [0]
    LIM = 6.0
    for k, (a, b) in enumerate(pairs):
        d = df[(df.group_a == a) & (df.group_b == b)].set_index("feature").reindex(keep)
        yy = np.arange(len(keep)) + offs[k]
        g = d["hedges_g"].clip(-LIM, LIM)
        lo = d["ci_low"].clip(-LIM, LIM)
        hi = d["ci_high"].clip(-LIM, LIM)
        col = PALETTE[k % len(PALETTE)]
        ax.errorbar(g, yy, xerr=[(g - lo).clip(lower=0), (hi - g).clip(lower=0)], fmt="o", ms=4, capsize=2, color=col,
                    label=f"{a} vs {b}")
        for y_, gv in zip(yy, d["hedges_g"]):
            if np.isfinite(gv) and abs(gv) > LIM:
                ax.annotate(f"{gv:.0f}", (np.sign(gv) * LIM, y_), xytext=(4 * np.sign(gv), 0), textcoords="offset points",
                            ha="left" if gv > 0 else "right", va="center", fontsize=7, color=col)
    ax.set_xlim(-LIM * 1.15, LIM * 1.15)
    ax.axvline(0, color="#9aa5b1", lw=0.8)
    ax.set_yticks(range(len(keep)))
    ax.set_yticklabels([measures.GROUPS.get(f, ("", f))[1] for f in keep])
    ax.invert_yaxis()
    ax.set_xlabel("Hedges' g (positive: first group higher) with bootstrap 95 % CI")
    ax.set_title("Largest differences between groups (singer-level)")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    return _save(fig, out, "fig_effect_sizes")


def fig_pitch_hist(s, df, out, colors):
    plt = _plt()
    segs = df[(df.kind == "phrase")][["segment", "sample", "group"]].drop_duplicates()
    if segs.empty:
        return None
    c = s.constants()
    data = {}
    for _, r in segs.iterrows():
        smp = service.sample(s, int(r["sample"]))
        if not smp["tonic_hz"]:
            continue
        seg = s.one("SELECT * FROM segments WHERE id=?", (int(r["segment"]),))
        src, _ = service.measure_source(s, smp["id"])
        y, sr = audio_io.segment(src, seg["start"], seg["end"])
        _, f0 = measures.pitch_track(y, sr, c, smp["meta"].get("voice_type", ""))
        cts = measures.cents(f0, smp["tonic_hz"])
        data.setdefault(r["group"], []).append(cts[np.isfinite(cts)])
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    bins = np.arange(-1250, 2410, 10)
    for g, arrs in data.items():
        v = np.concatenate(arrs)
        h, e = np.histogram(v, bins=bins, density=True)
        ax.plot(e[:-1] + 5, h, color=colors.get(g, "#333"), lw=1.2, label=f"{g} (n frames={len(v)})")
    for k in range(-1200, 2401, 100):
        ax.axvline(k, color="#e4e7eb", lw=0.5, zorder=0)
    ax.set_xticks(range(-1200, 2401, 300))
    ax.set_xlabel("Pitch relative to tonic (cents; 0 = Sa / key note, 1200 = upper octave)")
    ax.set_ylabel("Density")
    ax.set_title("Pitch distribution relative to the tonic")
    ax.legend(frameon=False, fontsize=8)
    return _save(fig, out, "fig_pitch_distribution")


def _singer_level(df, features):
    d = df[df.feature.isin(features)]
    return d.groupby(["group", "singer", "feature"])["value"].mean().unstack("feature").reset_index()


def fig_scatter(df, out, colors, fx, fy, title, name, xlab=None, ylab=None):
    plt = _plt()
    w = _singer_level(df, [fx, fy])
    if w.empty or fx not in w or fy not in w:
        return None
    w = w.dropna(subset=[fx, fy])
    if w.empty:
        return None
    fig, ax = plt.subplots(figsize=(4.6, 3.6))
    for g, d in w.groupby("group"):
        ax.scatter(d[fx], d[fy], s=28, color=colors.get(g, "#333"), label=g, alpha=0.85, edgecolor="white", lw=0.5)
    ax.set_xlabel(xlab or f"{measures.GROUPS[fx][1]} ({measures.UNITS[fx]})")
    ax.set_ylabel(ylab or f"{measures.GROUPS[fy][1]} ({measures.UNITS[fy]})")
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=8)
    return _save(fig, out, name)


def fig_vowels(df, out, colors):
    plt = _plt()
    d = df[(df.kind == "vowel") & df.feature.isin(["f1_hz", "f2_hz"])]
    if d.empty:
        return None
    w = d.pivot_table(index=["group", "segment"], columns="feature", values="value").reset_index().dropna()
    if w.empty or "f1_hz" not in w or "f2_hz" not in w:
        return None
    fig, ax = plt.subplots(figsize=(4.6, 3.8))
    for g, x in w.groupby("group"):
        ax.scatter(x["f2_hz"], x["f1_hz"], s=18, color=colors.get(g, "#333"), label=g, alpha=0.8)
    ax.invert_xaxis()
    ax.invert_yaxis()
    ax.set_xlabel("F2 (Hz)")
    ax.set_ylabel("F1 (Hz)")
    ax.set_title("Vowel space of held vowels (F1–F2)")
    ax.legend(frameon=False, fontsize=8)
    return _save(fig, out, "fig_vowel_space")


def fig_ltas(s, df, out, colors):
    plt = _plt()
    segs = df[df.kind.isin(["vowel", "phrase"])][["segment", "sample", "group"]].drop_duplicates()
    if segs.empty:
        return None
    spectra = {}
    for _, r in segs.iterrows():
        seg = s.one("SELECT * FROM segments WHERE id=?", (int(r["segment"]),))
        src, _ = service.measure_source(s, int(r["sample"]))
        y, sr = audio_io.segment(src, seg["start"], seg["end"])
        if len(y) < sr * 0.3:
            continue
        f, p = measures.ltas(y, sr, 50.0)
        m = f <= 8000
        db = 10 * np.log10(p[m] + 1e-20)
        spectra.setdefault(r["group"], []).append(db - db.max())
        fr = f[m]
    if not spectra:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.axvspan(2000, 4000, color="#fde68a", alpha=0.35, lw=0, label="singer's-formant band")
    for g, arr in spectra.items():
        ax.plot(fr, np.mean(arr, axis=0), color=colors.get(g, "#333"), lw=1.2, label=f"{g} (n={len(arr)})")
    ax.set_xscale("log")
    ax.set_xlim(60, 8000)
    ax.set_xticks([100, 250, 500, 1000, 2000, 4000, 8000])
    ax.set_xticklabels(["100", "250", "500", "1k", "2k", "4k", "8k"])
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Level re peak (dB)")
    ax.set_title("Long-term average spectrum by group")
    ax.legend(frameon=False, fontsize=8)
    return _save(fig, out, "fig_ltas")


def fig_box(df, out, colors, features, title, name):
    plt = _plt()
    sl = df[df.feature.isin(features)].groupby(["group", "singer", "feature"])["value"].mean().reset_index()
    feats = [f for f in features if f in sl.feature.unique()]
    if not feats:
        return None
    groups = sorted(sl.group.unique())
    fig, axes = plt.subplots(1, len(feats), figsize=(2.4 * len(feats) + 0.6, 3.0), squeeze=False)
    for ax, f in zip(axes[0], feats):
        data = [sl[(sl.feature == f) & (sl.group == g)]["value"].to_numpy() for g in groups]
        bp = ax.boxplot(data, widths=0.5, patch_artist=True, showfliers=False)
        for patch, g in zip(bp["boxes"], groups):
            patch.set_facecolor(colors.get(g, "#ccc"))
            patch.set_alpha(0.35)
        for i, d in enumerate(data, 1):
            ax.scatter(np.full(len(d), i) + np.random.default_rng(i).uniform(-0.12, 0.12, len(d)), d, s=10,
                       color=colors.get(groups[i - 1], "#333"), zorder=3)
        ax.set_xticks(range(1, len(groups) + 1))
        ax.set_xticklabels(groups, rotation=30, ha="right", fontsize=8)
        ax.set_title(f"{measures.GROUPS[f][1]}", fontsize=8.5)
        ax.set_ylabel(measures.UNITS[f])
    fig.suptitle(title, x=0.02, ha="left", fontweight="bold", fontsize=10)
    fig.tight_layout()
    return _save(fig, out, name)


def fig_tempo(s, out, colors):
    plt = _plt()
    from . import rhythm
    rows = s.q("SELECT DISTINCT cycles.sample_id, groups.name g FROM cycles JOIN samples ON samples.id=cycles.sample_id "
               "JOIN groups ON groups.id=samples.group_id WHERE cycles.kind='cycle' AND cycles.source='manual'")
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    used = set()
    for r in rows:
        t = [m["t"] for m in service.marks(s, r["sample_id"]) if m["kind"] == "cycle" and m["source"] == "manual"]
        tc = rhythm.tempo_curve(t)
        if len(tc) < 2:
            continue
        lab = r["g"] if r["g"] not in used else None
        used.add(r["g"])
        ax.plot([x["t"] for x in tc], [x["bpm"] for x in tc], marker="o", ms=3, lw=1, color=colors.get(r["g"], "#333"),
                label=lab)
    if not used:
        plt.close(fig)
        return None
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Cycles per minute")
    ax.set_title("Tempo curve per marked tala / bar cycle")
    ax.legend(frameon=False, fontsize=8)
    return _save(fig, out, "fig_tempo_curves")


def fig_pca(cmp, out, colors):
    plt = _plt()
    p = cmp.get("pca")
    if not p:
        return None
    fig, ax = plt.subplots(figsize=(4.8, 3.8))
    for g in sorted({x["group"] for x in p["points"]}):
        pts = [x for x in p["points"] if x["group"] == g]
        ax.scatter([x["pc1"] for x in pts], [x["pc2"] for x in pts], s=30, color=colors.get(g, "#333"), label=g)
    ax.axhline(0, color="#e4e7eb", lw=0.8)
    ax.axvline(0, color="#e4e7eb", lw=0.8)
    ax.set_xlabel(f"PC1 ({p['explained'][0] * 100:.0f} % of variance)")
    ax.set_ylabel(f"PC2 ({p['explained'][1] * 100:.0f} %)")
    ax.set_title(f"Style map of singers ({p['n_features']} features)")
    ax.legend(frameon=False, fontsize=8)
    return _save(fig, out, "fig_style_map")


def fig_exhibits(s, df, out, colors):
    """One annotated spectrogram per group: first phrase segment, pitch contour and reviewed ornaments marked."""
    plt = _plt()
    paths = []
    import librosa
    import librosa.display  # noqa: F401
    for g in sorted(df["group"].unique()):
        seg_ids = df[(df.group == g) & (df.kind == "phrase")]["segment"].unique()
        if not len(seg_ids):
            continue
        seg = s.one("SELECT * FROM segments WHERE id=?", (int(seg_ids[0]),))
        smp = service.sample(s, seg["sample_id"])
        src, _ = service.measure_source(s, smp["id"])
        end = min(seg["end"], seg["start"] + 12)
        y, sr = audio_io.segment(src, seg["start"], end)
        S = librosa.amplitude_to_db(np.abs(librosa.stft(y, n_fft=2048, hop_length=256)), ref=np.max)
        fig, ax = plt.subplots(figsize=(7.2, 3.2))
        librosa.display.specshow(S, sr=sr, hop_length=256, x_axis="time", y_axis="log", ax=ax, cmap="magma", vmin=-80)
        t, f0 = measures.pitch_track(y, sr, s.constants(), smp["meta"].get("voice_type", ""))
        f = np.where(f0 > 0, f0, np.nan)
        ax.plot(t, f, color="#38bdf8", lw=1.2, label="F0")
        if smp["tonic_hz"]:
            ax.axhline(smp["tonic_hz"], color="white", ls="--", lw=0.8)
            ax.text(0.05, smp["tonic_hz"] * 1.04, "tonic", color="white", fontsize=7)
        orn = s.q("SELECT * FROM ornaments WHERE segment_id=?", (seg["id"],))
        for o in orn:
            lab = o["final_label"] or o["auto_label"]
            a, b = o["start"] - seg["start"], o["end"] - seg["start"]
            if b < 0 or a > end - seg["start"]:
                continue
            ax.axvspan(max(a, 0), b, ymin=0.92, ymax=0.98, color="#22c55e" if lab == "vibrato" else "#f97316", alpha=0.9)
        ax.set_ylim(60, 8000)
        ax.set_title(f"{g}: {smp['code']} {seg['start']:.1f}–{end:.1f} s (green bar = vibrato, orange = ornament)")
        notes = s.q("SELECT text FROM notes WHERE segment_id=?", (seg["id"],))
        if notes:
            fig.text(0.01, -0.04, "Note: " + notes[0]["text"][:220], fontsize=7.5, style="italic")
        paths.append(_save(fig, out, f"fig_exhibit_{len(paths) + 1}"))
    return paths


# ------------------------------------------------------------------ main
def build(s, groups=None, style="APA 7", kind=None, section=None, progress=None):
    t0 = time.time()
    info = s.info()
    run = service.latest_run(s)
    if not run:
        raise ValueError("Run the analysis first (Analyse tab).")
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = s.folder / "reports" / f"report_{stamp}"
    figdir = out / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    df = service.results_frame(s, run["id"], kind=kind, section=section)
    if groups:
        df = df[df.group.isin(groups)]
    if df.empty:
        raise ValueError("No results for the chosen groups and filters.")
    bias = {k: {"mean_shift": v["mean_shift"], "sd_shift": v["sd_shift"]} for k, v in service.bias_table(s).items()}
    if progress:
        progress(0.1, "Statistics")
    cmp = stats.compare(df[["group", "singer", "feature", "value"]], bias=bias or None)
    colors = _colors(cmp["groups"])
    figs = {}
    steps = [
        ("effects", lambda: fig_effects(cmp, figdir)),
        ("pitch", lambda: fig_pitch_hist(s, df, figdir, colors)),
        ("vibrato", lambda: fig_scatter(df, figdir, colors, "vibrato_rate_hz", "vibrato_extent_cents",
                                        "Vibrato rate and extent (singer means)", "fig_vibrato")),
        ("ltas", lambda: fig_ltas(s, df, figdir, colors)),
        ("vowels", lambda: fig_vowels(df, figdir, colors)),
        ("cpps", lambda: fig_scatter(df, figdir, colors, "f0_median_hz", "cpps_db", "CPPS against F0 (held vowels)",
                                     "fig_cpps_f0")),
        ("hnr", lambda: fig_scatter(df, figdir, colors, "intensity_mean_db", "hnr_db", "HNR against loudness (held vowels)",
                                    "fig_hnr_loudness")),
        ("voice", lambda: fig_box(df, figdir, colors, ["hnr_db", "cpps_db", "jitter_detrended_pct", "shimmer_local_pct"],
                                  "Voice quality by group (singer means)", "fig_voice_quality")),
        ("envelope", lambda: fig_box(df, figdir, colors, ["attack_ms", "release_ms", "sustain_db"],
                                     "Note envelope by group (singer means)", "fig_envelope")),
        ("rhythm", lambda: fig_box(df, figdir, colors, ["note_rate_per_s", "ioi_cv", "npvi"],
                                   "Rhythmic variety by group (singer means)", "fig_rhythm")),
        ("tempo", lambda: fig_tempo(s, figdir, colors)),
        ("pca", lambda: fig_pca(cmp, figdir, colors)),
        ("exhibits", lambda: fig_exhibits(s, df, figdir, colors)),
    ]
    fig_errors = {}
    for i, (k, fn) in enumerate(steps):
        if progress:
            progress(0.15 + 0.55 * i / len(steps), f"Figure: {k}")
        try:
            figs[k] = fn()
        except Exception as e:
            fig_errors[k] = f"{type(e).__name__}: {e}"[:200]
    if progress:
        progress(0.75, "Tables")
    desc = pd.DataFrame(cmp["describe"])
    pair = pd.DataFrame(cmp["pairwise"])
    tests = pd.DataFrame(cmp["tests"])
    desc.to_csv(out / "descriptives.csv", index=False)
    pair.to_csv(out / "pairwise_effects.csv", index=False)
    tests.to_csv(out / "group_tests.csv", index=False)
    df.drop(columns=["meta"], errors="ignore").to_csv(out / "segment_results.csv", index=False)
    corpus = corpus_table(s)
    corpus.to_csv(out / "corpus.csv", index=False)
    excl = pd.DataFrame(service.exclusion_log(s))
    excl.to_csv(out / "exclusion_log.csv", index=False)
    with pd.ExcelWriter(out / "sonicdiff_results.xlsx") as xw:
        desc.to_excel(xw, "Descriptives", index=False)
        pair.to_excel(xw, "Pairwise effects", index=False)
        tests.to_excel(xw, "Group tests", index=False)
        corpus.to_excel(xw, "Corpus", index=False)
        excl.to_excel(xw, "Exclusions", index=False)
    (out / "tables.tex").write_text(latex_tables(desc, pair, tests), encoding="utf-8")
    (out / "references.bib").write_text(citations.bibtex(), encoding="utf-8")
    meth = methods_text(s, run, cmp)
    (out / "methods_appendix.txt").write_text(meth, encoding="utf-8")
    hashes = s.q("SELECT code, filename, sha256 FROM samples ORDER BY id")
    (out / "reproducibility.json").write_text(json.dumps({"sonicdiff": VERSION, "run": run, "constants": s.constants(),
                                                          "files": hashes}, indent=2, default=str), encoding="utf-8")
    if progress:
        progress(0.85, "Word document")
    docx_path = write_docx(s, out, info, run, cmp, figs, style, meth, corpus, kind, section)
    if progress:
        progress(0.93, "PDF")
    pdf_path = write_pdf(s, out, info, run, cmp, figs, style, meth)
    summary = {"folder": str(out), "docx": str(docx_path), "pdf": str(pdf_path), "level": cmp["level"],
               "groups": cmp["groups"], "n_singers": cmp["n_singers"], "figures": sorted(p.name for p in figdir.glob("*.png")),
               "figure_errors": fig_errors, "seconds": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    s.log("report", summary)
    if progress:
        progress(1.0, "Done")
    return summary


def corpus_table(s):
    rows = []
    for r in service.samples(s):
        m = r["meta"]
        singers = s.q("SELECT DISTINCT singers.code FROM segments JOIN singers ON singers.id=segments.singer_id "
                      "WHERE segments.sample_id=?", (r["id"],))
        rows.append({"code": r["code"], "group": r["group_name"], "file": r["filename"], "piece": m.get("piece", ""),
                     "raga_tala_or_work": m.get("raga_or_work", ""), "performer": m.get("performer", ""),
                     "singers": ", ".join(x["code"] for x in singers), "voice_type": m.get("voice_type", ""),
                     "source": m.get("source", ""), "licence_rights": m.get("rights", ""),
                     "duration_s": round(r["duration"] or 0, 1), "qc": r["qc_status"],
                     "tonic_hz": r["tonic_hz"], "tonic_confirmed": bool(r["tonic_confirmed"]),
                     "measured_from": m.get("measure_from", "measurement copy"), "sha256": r["sha256"]})
    return pd.DataFrame(rows)


def latex_tables(desc, pair, tests):
    def esc(x):
        return str(x).replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")

    def tab(df, cols, cap, lab):
        if df.empty:
            return f"% {cap}: no data\n"
        lines = [r"\begin{table}[htbp]\centering\small", f"\\caption{{{esc(cap)}}}\\label{{{lab}}}",
                 r"\begin{tabular}{" + "l" * len(cols) + "}", r"\hline",
                 " & ".join(esc(c) for c in cols) + r" \\ \hline"]
        for _, r in df[cols].iterrows():
            vals = [f"{v:.3g}" if isinstance(v, (float, np.floating)) and np.isfinite(v) else esc(v if v is not None else "")
                    for v in r]
            lines.append(" & ".join(vals) + r" \\")
        lines += [r"\hline", r"\end{tabular}", r"\end{table}", ""]
        return "\n".join(lines)
    out = tab(desc, [c for c in ["group", "feature", "unit", "n_singers", "mean", "sd", "median"] if c in desc],
              "Descriptive statistics (singer means)", "tab:descriptives")
    if not pair.empty and "hedges_g" in pair:
        out += tab(pair.dropna(subset=["hedges_g"]), ["group_a", "group_b", "feature", "hedges_g", "ci_low", "ci_high"],
                   "Pairwise effect sizes", "tab:effects")
    if not tests.empty:
        out += tab(tests, [c for c in ["feature", "test", "p", "q_fdr"] if c in tests], "Group-effect tests", "tab:tests")
    return out


def methods_text(s, run, cmp):
    v = json.loads(run["versions"])
    c = s.constants()
    lines = [
        f"Analysis performed with VU3INI SonicDiff {v.get('sonicdiff')} (run {run['id']}, "
        f"{dt.datetime.fromtimestamp(run['started']).strftime('%d %B %Y')}).",
        f"Software: Python {v.get('python')}, Praat {v.get('praat')} via Parselmouth {v.get('parselmouth')}, "
        f"librosa {v.get('librosa')}, NumPy {v.get('numpy')}, SciPy {v.get('scipy')}, statsmodels {v.get('statsmodels')}. "
        f"Separation: {v.get('separation')}.",
        f"Audio: every file was converted to a measurement copy (mono, {c['audio']['sample_rate']} Hz, DC removed, "
        f"{c['audio']['highpass_hz']:.0f} Hz fourth-order zero-phase high-pass). A noise-reduced guide copy was used only to "
        "locate segments, notes and onsets; all values were measured on the measurement copy (or on the separated vocal stem "
        "where stated, with the remix-test bias reported).",
        f"Pitch: Praat autocorrelation, time step {c['pitch']['time_step_s'] * 1000:.0f} ms, range "
        f"{c['pitch']['floor_male_hz']:.0f}–{c['pitch']['ceiling_male_hz']:.0f} Hz (male) and "
        f"{c['pitch']['floor_female_hz']:.0f}–{c['pitch']['ceiling_female_hz']:.0f} Hz (female); cents relative to the "
        "researcher-confirmed tonic, 1200·log2(F0/tonic).",
        f"Vibrato: held notes of at least {c['vibrato']['min_note_s']} s; rate from the autocorrelation peak in "
        f"{c['vibrato']['rate_min_hz']}–{c['vibrato']['rate_max_hz']} Hz; extent from a least-squares sinusoid fit.",
        f"Formants: Praat Burg, {c['formant']['n_formants']} formants, ceiling {c['formant']['max_formant_male_hz']:.0f} Hz "
        f"(male) / {c['formant']['max_formant_female_hz']:.0f} Hz (female), window {c['formant']['window_s'] * 1000:.0f} ms.",
        f"Voice quality on the central {c['segments']['vowel_core_fraction'] * 100:.0f} % of held vowels: HNR (Praat "
        f"cross-correlation, min pitch {c['hnr']['min_pitch_hz']:.0f} Hz); CPPS (Praat PowerCepstrogram, time step "
        f"{c['cpps']['time_step_s'] * 1000:.0f} ms, smoothing {c['cpps']['time_smoothing_s'] * 1000:.0f} ms × "
        f"{c['cpps']['quefrency_smoothing_s'] * 1000:.0f} ms, peak search ±50 % around the segment's median F0, robust "
        "straight trend line); jitter and shimmer (local, Praat defaults); detrended jitter after removing the slow "
        "(vibrato) movement of the period sequence (Savitzky–Golay, 11 periods).",
        f"Timbre: long-term average spectrum ({c['spectral']['ltas_bandwidth_hz']:.0f} Hz bandwidth); singer's-formant "
        "energy as the 2–4 kHz level re 0–2 kHz; spectral tilt as the regression slope of level against log2 frequency "
        f"(100 Hz–5 kHz); MFCC {c['spectral']['n_mfcc']} coefficients, {c['spectral']['n_mels']} mel bands.",
        "Rhythm: onsets from the accompaniment stem or guide copy; inter-onset-interval CV and nPVI; tempo and "
        "syncopation only from researcher-confirmed beats and tala/bar cycles.",
        f"Statistics: segment values were averaged per singer. Statistics level: {cmp['level']} "
        f"(smallest group has {min(cmp['n_singers'].values()) if cmp['n_singers'] else 0} singers). {cmp['level_text']} "
        "Effect sizes are Hedges' g with 2000-sample bootstrap 95 % confidence intervals; group effects use "
        "likelihood-ratio tests of random-intercept mixed models (inferential level) or Kruskal–Wallis tests on singer "
        "means (exploratory level), with Benjamini–Hochberg FDR control.",
        f"Constants hash: {run['constants_hash']}. File SHA-256 hashes are listed in reproducibility.json.",
    ]
    return "\n\n".join(lines) + "\n"


GLOSSARY = [
    ("Swara", "A note of the Indian scale, named relative to the tonic Sa."),
    ("Sa / tonic", "The reference pitch chosen by the performer; all accompaniment is tuned to it."),
    ("Meend", "A continuous glide between notes."),
    ("Gamak", "A wide, often fast pitch oscillation used as an ornament."),
    ("Andolan", "A slow, gentle oscillation of a note."),
    ("Tala", "A rhythmic cycle of fixed length."),
    ("Cents", "1/100 of an equal-tempered semitone; 1200 cents = one octave."),
    ("Singer's formant", "A cluster of energy near 2.5–3.5 kHz in trained classical voices."),
    ("HNR", "Harmonics-to-noise ratio: periodic versus noise energy, in dB."),
    ("CPPS", "Smoothed cepstral peak prominence: how strongly periodic the voice is, in dB."),
    ("Jitter / shimmer", "Cycle-to-cycle variation of period / amplitude."),
    ("nPVI", "Normalised pairwise variability index of successive durations."),
    ("Hedges' g", "Standardised mean difference corrected for small samples."),
    ("FDR", "False-discovery rate, controlled with the Benjamini–Hochberg procedure."),
]


def _md_runs(p, text):
    """Add text to a python-docx paragraph, turning *x* into italics."""
    import re
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text):
        if not part:
            continue
        if part.startswith("**"):
            p.add_run(part[2:-2]).bold = True
        elif part.startswith("*"):
            p.add_run(part[1:-1]).italic = True
        else:
            p.add_run(part)


def _fmt(v, nd=3):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "–"
    if isinstance(v, (int, np.integer)):
        return str(v)
    if isinstance(v, (float, np.floating)):
        a = abs(v)
        if a >= 100:
            return f"{v:,.0f}"
        if a >= 1:
            return f"{v:.{max(0, nd - 1 - int(np.floor(np.log10(a))))}f}"
        if a >= 0.001:
            return f"{v:.{nd}f}"
        return f"{v:.1e}"
    return str(v)


def write_docx(s, out, info, run, cmp, figs, style, meth, corpus, kind, section):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    for sec in doc.sections:
        sec.left_margin = sec.right_margin = Cm(2.2)
        fp = sec.footer.paragraphs[0]
        fp.text = f"By Sasanka Boruah -VU3INI · VU3INI SonicDiff {VERSION}"
        fp.runs[0].font.size = Pt(8)
    logo = ASSETS / "logo.png"
    if logo.exists():
        doc.add_picture(str(logo), width=Cm(2.6))
    doc.add_heading(f"{info['name']}: acoustic comparison report", 0)
    p = doc.add_paragraph()
    p.add_run(f"Generated {dt.datetime.now().strftime('%d %B %Y %H:%M')} by VU3INI SonicDiff {VERSION}, analysis run "
              f"{run['id']}. ").italic = True
    filt = ", ".join(x for x in [f"segment kind: {kind}" if kind else "", f"section: {section}" if section else ""] if x)
    if filt:
        p.add_run(f"Filter: {filt}.").italic = True

    doc.add_heading("1. Summary", 1)
    doc.add_paragraph(f"Groups compared: {', '.join(cmp['groups'])}. Distinct singers per group: "
                      + ", ".join(f"{g} {n}" for g, n in cmp["n_singers"].items()) + ".")
    pp = doc.add_paragraph()
    pp.add_run(f"Statistics level: {cmp['level']}. ").bold = True
    pp.add_run(cmp["level_text"])
    top = sorted([r for r in cmp["pairwise"] if r.get("hedges_g") is not None], key=lambda r: -abs(r["hedges_g"]))[:8]
    if top:
        doc.add_paragraph("Largest singer-level differences (Hedges' g, 95 % CI):")
        for r in top:
            ci = f" [{_fmt(r.get('ci_low'), 2)}, {_fmt(r.get('ci_high'), 2)}]" if r.get("ci_low") is not None else ""
            b = f"; separation bias {_fmt(r.get('bias_mean'), 2)} ± {_fmt(r.get('bias_sd'), 2)}" if r.get("bias_mean") is not None else ""
            doc.add_paragraph(f"{measures.GROUPS.get(r['feature'], ('', r['feature']))[1]}: {r['group_a']} "
                              f"{_fmt(r['mean_a'])} vs {r['group_b']} {_fmt(r['mean_b'])} {r['unit']}; "
                              f"g = {_fmt(r['hedges_g'], 2)}{ci}{b}", style="List Bullet")
    doc.add_paragraph("These results describe stylistic difference, not quality. No tradition is ranked above another.")

    def add_fig(key, caption):
        f = figs.get(key)
        if not f:
            return
        for x in (f if isinstance(f, list) else [f]):
            doc.add_picture(str(x), width=Cm(16) if "exhibit" in str(x) or key in ("effects", "pitch", "ltas", "tempo") else Cm(11))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            c = doc.add_paragraph(caption)
            c.alignment = WD_ALIGN_PARAGRAPH.CENTER
            c.runs[0].italic = True
            c.runs[0].font.size = Pt(9)

    doc.add_heading("2. Quantitative results", 1)
    add_fig("effects", "Figure: Effect sizes between groups (singer means).")
    groups_order = ["Pitch", "Vibrato", "Loudness", "Timbre", "Formants", "Voice quality", "Harmonics", "Envelope", "Rhythm"]
    desc = pd.DataFrame(cmp["describe"])
    if not desc.empty:
        desc["fgroup"] = desc.feature.map(lambda f: measures.GROUPS.get(f, ("Other", f))[0])
        for fg in groups_order:
            d = desc[desc.fgroup == fg]
            if d.empty:
                continue
            doc.add_heading(fg, 2)
            gs = cmp["groups"]
            t = doc.add_table(rows=1, cols=1 + len(gs))
            t.style = "Light Grid Accent 1"
            t.rows[0].cells[0].text = "Feature (unit)"
            for i, g in enumerate(gs):
                t.rows[0].cells[i + 1].text = f"{g}\nmean ± SD (n singers)"
            for f in [x for x in measures.UNITS if x in set(d.feature)]:
                row = t.add_row().cells
                row[0].text = f"{measures.GROUPS[f][1]} ({measures.UNITS[f]})" if measures.UNITS[f] else measures.GROUPS[f][1]
                for i, g in enumerate(gs):
                    x = d[(d.feature == f) & (d.group == g)]
                    if len(x):
                        r = x.iloc[0]
                        row[i + 1].text = f"{_fmt(r['mean'])} ± {_fmt(r['sd'])} ({r['n_singers']})"
            for row in t.rows:
                for c in row.cells:
                    for pp_ in c.paragraphs:
                        for rr in pp_.runs:
                            rr.font.size = Pt(8)
            fig_map = {"Pitch": ("pitch", "Figure: Pitch distribution relative to the tonic."),
                       "Vibrato": ("vibrato", "Figure: Vibrato rate against extent."),
                       "Timbre": ("ltas", "Figure: Long-term average spectra with the singer's-formant band."),
                       "Formants": ("vowels", "Figure: Vowel space of held vowels."),
                       "Voice quality": ("voice", "Figure: Voice-quality measures by group."),
                       "Envelope": ("envelope", "Figure: Note envelope by group."),
                       "Rhythm": ("rhythm", "Figure: Rhythmic variety by group.")}
            if fg in fig_map:
                add_fig(*fig_map[fg])
            if fg == "Voice quality":
                add_fig("cpps", "Figure: CPPS against F0. CPPS depends on F0 and loudness; read differences with these.")
                add_fig("hnr", "Figure: HNR against loudness.")
            if fg == "Rhythm":
                add_fig("tempo", "Figure: Tempo per marked cycle.")
    tests = cmp["tests"]
    if tests:
        doc.add_heading("Group-effect tests", 2)
        t = doc.add_table(rows=1, cols=4)
        t.style = "Light Grid Accent 1"
        for i, h in enumerate(["Feature", "Test", "p", "q (FDR)"]):
            t.rows[0].cells[i].text = h
        for r in sorted(tests, key=lambda r: (r.get("q_fdr") is None, r.get("q_fdr") or 1)):
            c = t.add_row().cells
            c[0].text = measures.GROUPS.get(r["feature"], ("", r["feature"]))[1]
            c[1].text = r["test"]
            c[2].text = _fmt(r.get("p"))
            c[3].text = _fmt(r.get("q_fdr"))
    add_fig("pca", "Figure: Style map of singers (principal components of all features).")

    doc.add_heading("3. Qualitative exhibits", 1)
    doc.add_paragraph("Representative phrase per group, with the pitch contour (blue), the tonic (dashed) and reviewed "
                      "vibrato / ornament events marked along the top.")
    add_fig("exhibits", "Figure: Annotated spectrogram exhibit.")
    notes = s.q("SELECT notes.*, segments.start, samples.code FROM notes LEFT JOIN segments ON segments.id=notes.segment_id "
                "LEFT JOIN samples ON samples.id=COALESCE(notes.sample_id, segments.sample_id) ORDER BY notes.kind, notes.id")
    if notes:
        doc.add_heading("Researcher's notes", 2)
        for n in notes:
            where = f"{n['code'] or ''} {('at ' + format(n['start'], '.1f') + ' s') if n['start'] is not None else ''}".strip()
            doc.add_paragraph(f"[{n['kind']}] {where}: {n['text']}", style="List Bullet")
    orn = s.q("SELECT groups.name g, COALESCE(final_label, auto_label) lab, COUNT(*) n FROM ornaments JOIN segments ON "
              "segments.id=ornaments.segment_id JOIN samples ON samples.id=segments.sample_id JOIN groups ON "
              "groups.id=samples.group_id GROUP BY g, lab")
    if orn:
        doc.add_heading("Pitch oscillations: vibrato and ornament events", 2)
        for o in orn:
            doc.add_paragraph(f"{o['g']}: {o['n']} {o['lab']} events", style="List Bullet")
    doc.add_heading("Glossary", 2)
    for k, v in GLOSSARY:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(k + ": ").bold = True
        p.add_run(v)

    doc.add_heading("Appendix A. Methods", 1)
    for para in meth.strip().split("\n\n"):
        doc.add_paragraph(para)
    doc.add_heading("Appendix B. Corpus", 1)
    cols = ["code", "group", "piece", "performer", "singers", "voice_type", "source", "qc", "tonic_hz"]
    t = doc.add_table(rows=1, cols=len(cols))
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(cols):
        t.rows[0].cells[i].text = h
    for _, r in corpus.iterrows():
        c = t.add_row().cells
        for i, h in enumerate(cols):
            c[i].text = _fmt(r[h]) if h == "tonic_hz" else str(r[h] if r[h] is not None else "")
    for row in t.rows:
        for c in row.cells:
            for pp_ in c.paragraphs:
                for rr in pp_.runs:
                    rr.font.size = Pt(7.5)
    doc.add_heading("Appendix C. Exclusion log", 1)
    ex = service.exclusion_log(s)
    if ex:
        for e in ex:
            doc.add_paragraph(f"{dt.datetime.fromtimestamp(e['time']).strftime('%Y-%m-%d')} · {e['action']} · "
                              + ", ".join(f"{k}: {v}" for k, v in e.items() if k not in ("time", "action")), style="List Bullet")
    else:
        doc.add_paragraph("No samples or segments were excluded.")
    doc.add_heading("Appendix D. Reproducibility", 1)
    doc.add_paragraph(f"Constants hash {run['constants_hash']}; SonicDiff {VERSION}. Every input file's SHA-256 hash, the "
                      "full constants and software versions are in reproducibility.json beside this report.")
    doc.add_heading(f"References ({style})", 1)
    for ref in citations.reference_list(style):
        p = doc.add_paragraph()
        _md_runs(p, ref)
    doc.add_paragraph("Check every reference against its source before submission.").runs[0].italic = True
    path = out / "SonicDiff_report.docx"
    doc.save(str(path))
    return path


def write_pdf(s, out, info, run, cmp, figs, style, meth):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    import re

    ss = getSampleStyleSheet()
    path = out / "SonicDiff_report.pdf"

    def footer(c, d):
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.grey)
        c.drawString(2 * cm, 1.2 * cm, f"By Sasanka Boruah -VU3INI · VU3INI SonicDiff {VERSION}")
        c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {d.page}")

    def P(text, st="BodyText"):
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)
        return Paragraph(text, ss[st])

    el = []
    logo = ASSETS / "logo.png"
    if logo.exists():
        el.append(Image(str(logo), width=2.4 * cm, height=2.4 * cm))
    el += [P(f"{info['name']}: acoustic comparison report", "Title"),
           P(f"VU3INI SonicDiff {VERSION} · run {run['id']} · {dt.datetime.now().strftime('%d %B %Y')}"),
           Spacer(1, 8), P("Summary", "Heading1"),
           P(f"Groups: {', '.join(cmp['groups'])}. Singers per group: "
             + ", ".join(f"{g} {n}" for g, n in cmp["n_singers"].items()) + "."),
           P(f"**Statistics level: {cmp['level']}.** {cmp['level_text']}")]

    def addimg(p, w=16):
        from PIL import Image as PI
        with PI.open(p) as im:
            ratio = im.height / im.width
        el.append(Image(str(p), width=w * cm, height=w * cm * ratio))
        el.append(Spacer(1, 6))

    for k in ["effects", "pitch", "vibrato", "ltas", "vowels", "voice", "cpps", "hnr", "envelope", "rhythm", "tempo", "pca"]:
        f = figs.get(k)
        if f:
            addimg(f, 16 if k in ("effects", "pitch", "ltas", "tempo") else 11)
    rows = [["Group", "Feature", "Mean", "SD", "n"]]
    for r in cmp["describe"]:
        rows.append([r["group"], measures.GROUPS.get(r["feature"], ("", r["feature"]))[1][:40], _fmt(r["mean"]),
                     _fmt(r["sd"]), str(r["n_singers"])])
    el += [PageBreak(), P("Descriptive statistics (singer means)", "Heading1")]
    t = Table(rows, repeatRows=1, colWidths=[3 * cm, 7 * cm, 2.2 * cm, 2.2 * cm, 1.2 * cm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
    el.append(t)
    ex = figs.get("exhibits") or []
    if ex:
        el += [PageBreak(), P("Qualitative exhibits", "Heading1")]
        for f in ex:
            addimg(f, 16)
    el += [PageBreak(), P("Methods", "Heading1")] + [P(x) for x in meth.strip().split("\n\n")]
    el += [P(f"References ({style})", "Heading1")] + [P(r) for r in citations.reference_list(style)]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm,
                      bottomMargin=2 * cm, title=f"{info['name']} report", author="Sasanka Boruah -VU3INI").build(
        el, onFirstPage=footer, onLaterPages=footer)
    return path


def archive(s):
    """Zip the whole study folder for examiners."""
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = s.folder / "reports" / f"study_archive_{stamp}.zip"
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p in s.folder.rglob("*"):
            if p.is_file() and "study_archive_" not in p.name and p.suffix not in (".db-wal", ".db-shm"):
                z.write(p, p.relative_to(s.folder.parent))
    return dst
