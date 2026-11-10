"""Statistics (Phase 5).

The singer is the unit of analysis: segment values are averaged per singer
before any group comparison. The statistics level follows the smallest
number of distinct singers in the groups being compared:

  8 or more  -> 'inferential': mixed-effects model (random intercept per
                singer, segments as repeated measures), likelihood-ratio
                test of the group effect, Benjamini–Hochberg FDR.
  3 to 7     -> 'exploratory': effect sizes (Hedges' g) with bootstrap 95 %
                confidence intervals on singer means; p-values shown only
                with FDR and labelled exploratory.
  1 or 2     -> 'case study': per-singer profiles, no tradition-level tests.
"""
import itertools
import warnings

import numpy as np
import pandas as pd

from . import measures

warnings.filterwarnings("ignore")


def level_for(n_min):
    if n_min >= 8:
        return "inferential"
    if n_min >= 3:
        return "exploratory"
    return "case study"


LEVEL_TEXT = {
    "inferential": "Claims about the tradition (mixed-effects models, FDR-controlled).",
    "exploratory": "Exploratory: effect sizes with confidence intervals; not confirmatory.",
    "case study": "Case study: profiles of individual singers; no claims about the tradition as a whole.",
}


def hedges_g(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    sp = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    scale = max(abs(a.mean()), abs(b.mean()), 1e-12)
    if not np.isfinite(sp) or sp <= 1e-9 * scale:
        return None  # no variation within groups: a standardised difference is undefined
    d = (a.mean() - b.mean()) / sp
    return float(d * (1 - 3 / (4 * (na + nb) - 9)))


def boot_ci(a, b, n=2000, seed=7):
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return None, None
    gs = []
    for _ in range(n):
        g = hedges_g(rng.choice(a, len(a)), rng.choice(b, len(b)))
        if g is not None and np.isfinite(g):
            gs.append(g)
    if len(gs) < 100:
        return None, None
    return float(np.percentile(gs, 2.5)), float(np.percentile(gs, 97.5))


def singer_means(df):
    """df columns: group, singer, feature, value (segment level)."""
    return df.groupby(["group", "singer", "feature"], as_index=False)["value"].mean()


def describe(df_seg):
    sm = singer_means(df_seg)
    rows = []
    for (g, f), d in sm.groupby(["group", "feature"]):
        v = d["value"].to_numpy()
        nseg = int(((df_seg["group"] == g) & (df_seg["feature"] == f)).sum())
        rows.append({"group": g, "feature": f, "unit": measures.UNITS.get(f, ""), "n_singers": len(v), "n_segments": nseg,
                     "mean": float(np.mean(v)), "sd": float(np.std(v, ddof=1)) if len(v) > 1 else None,
                     "median": float(np.median(v)), "iqr": float(np.subtract(*np.percentile(v, [75, 25]))) if len(v) > 1 else None})
    return pd.DataFrame(rows)


def _lrt(d):
    """Likelihood-ratio test of the group effect in a random-intercept model."""
    import statsmodels.formula.api as smf
    from scipy import stats as st
    d = d.copy()
    d["y"] = (d["value"] - d["value"].mean()) / (d["value"].std() or 1.0)
    try:
        full = smf.mixedlm("y ~ C(group)", d, groups=d["singer"]).fit(reml=False, method="lbfgs")
        null = smf.mixedlm("y ~ 1", d, groups=d["singer"]).fit(reml=False, method="lbfgs")
        lr = 2 * (full.llf - null.llf)
        k = d["group"].nunique() - 1
        p = float(st.chi2.sf(max(lr, 0), k))
        params = {kk: float(v) for kk, v in full.fe_params.items()}
        return p, params, bool(full.converged)
    except Exception:
        return None, {}, False


def compare(df_seg, groups=None, bias=None):
    """Full comparison. Returns dict with level, descriptives, pairwise effects, model tests, PCA."""
    from statsmodels.stats.multitest import fdrcorrection
    if groups:
        df_seg = df_seg[df_seg["group"].isin(groups)]
    if df_seg.empty:
        return {"level": "case study", "level_text": LEVEL_TEXT["case study"], "groups": [], "n_singers": {},
                "describe": [], "pairwise": [], "tests": [], "pca": None}
    groups = sorted(df_seg["group"].unique())
    nsing = df_seg.groupby("group")["singer"].nunique().to_dict()
    nmin = min(nsing.values()) if nsing else 0
    level = level_for(nmin)
    desc = describe(df_seg)
    sm = singer_means(df_seg)

    pair_rows = []
    for g1, g2 in itertools.combinations(groups, 2):
        for f, d in sm.groupby("feature"):
            a = d[d.group == g1]["value"].to_numpy()
            b = d[d.group == g2]["value"].to_numpy()
            row = {"group_a": g1, "group_b": g2, "feature": f, "unit": measures.UNITS.get(f, ""),
                   "mean_a": float(a.mean()) if len(a) else None, "mean_b": float(b.mean()) if len(b) else None,
                   "diff": float(a.mean() - b.mean()) if len(a) and len(b) else None, "n_a": len(a), "n_b": len(b)}
            if level != "case study":
                g = hedges_g(a, b)
                lo, hi = boot_ci(a, b) if g is not None else (None, None)
                row.update(hedges_g=g, ci_low=lo, ci_high=hi)
            if bias and f in bias:
                row["bias_mean"] = bias[f]["mean_shift"]
                row["bias_sd"] = bias[f]["sd_shift"]
            pair_rows.append(row)

    tests = []
    if level != "case study" and len(groups) >= 2:
        from scipy import stats as st
        for f, d in df_seg.groupby("feature"):
            if d["group"].nunique() < 2:
                continue
            if level == "inferential":
                p, params, conv = _lrt(d)
                tests.append({"feature": f, "test": "mixed-effects LRT", "p": p, "converged": conv})
            else:
                s = sm[sm.feature == f]
                samples = [s[s.group == g]["value"].to_numpy() for g in groups]
                samples = [x for x in samples if len(x) >= 2]
                if len(samples) >= 2:
                    try:
                        p = float(st.kruskal(*samples).pvalue)
                    except Exception:
                        p = None
                    tests.append({"feature": f, "test": "Kruskal–Wallis on singer means", "p": p, "converged": True})
        ps = [t["p"] for t in tests if t["p"] is not None and np.isfinite(t["p"])]
        if ps:
            rej, q = fdrcorrection(ps, alpha=0.05)
            it = iter(zip(rej, q))
            for t in tests:
                if t["p"] is not None and np.isfinite(t["p"]):
                    r, qq = next(it)
                    t["q_fdr"] = float(qq)
                    t["significant_fdr"] = bool(r)

    pca = pca_map(sm)
    return {"level": level, "level_text": LEVEL_TEXT[level], "groups": groups, "n_singers": nsing,
            "describe": desc.to_dict("records"), "pairwise": pair_rows, "tests": tests, "pca": pca}


def pca_map(sm, min_cover=0.8):
    wide = sm.pivot_table(index=["group", "singer"], columns="feature", values="value")
    if wide.shape[0] < 3:
        return None
    keep = wide.columns[wide.notna().mean() >= min_cover]
    wide = wide[keep]
    wide = wide.fillna(wide.mean())
    wide = wide.loc[:, wide.std() > 0]
    if wide.shape[1] < 2:
        return None
    X = ((wide - wide.mean()) / wide.std()).to_numpy()
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    comp = U[:, :2] * S[:2]
    var = (S ** 2) / np.sum(S ** 2)
    load = sorted(zip(wide.columns, Vt[0]), key=lambda x: -abs(x[1]))[:6]
    return {"points": [{"group": g, "singer": s, "pc1": float(a), "pc2": float(b)}
                       for (g, s), (a, b) in zip(wide.index, comp)],
            "explained": [float(var[0]), float(var[1]) if len(var) > 1 else 0.0],
            "top_loadings_pc1": [{"feature": f, "loading": float(v)} for f, v in load],
            "n_features": int(wide.shape[1])}
