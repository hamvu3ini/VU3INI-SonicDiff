"""Study operations used by the web interface, the self-test and the command line."""
import hashlib
import json
import platform
import shutil
import time
from pathlib import Path

import numpy as np

from . import VERSION, audio_io, measures, ornament, prepare, qc, rhythm, separation, tonic
from .db import Study, sample_row, slugify
from .paths import projects_dir

_open = {}


# ------------------------------------------------------------------ studies
def list_studies():
    out = []
    for d in sorted(projects_dir().iterdir()):
        if (d / "study.db").exists():
            try:
                s = get(d.name)
                info = s.info() or {}
                n = s.one("SELECT COUNT(*) n FROM samples")["n"]
                out.append({"id": d.name, "name": info.get("name", d.name), "samples": n, "locked": bool(info.get("locked")),
                            "created": info.get("created")})
            except Exception as e:
                out.append({"id": d.name, "name": d.name, "error": str(e)})
    return out


def create_study(name, description="", groups=None):
    if not name or not name.strip():
        raise ValueError("A study needs a name.")
    sid = slugify(name)
    base, i = sid, 2
    while (projects_dir() / sid).exists():
        sid = f"{base}_{i}"
        i += 1
    s = Study(projects_dir() / sid)
    s.init(name.strip(), description)
    for g in groups or []:
        add_group(s, g.get("name"), g.get("tradition", ""), g.get("role", "study"))
    _open[sid] = s
    return sid


def get(sid):
    if sid not in _open:
        folder = projects_dir() / sid
        if not (folder / "study.db").exists():
            raise KeyError(f"No study called {sid}")
        _open[sid] = Study(folder)
    return _open[sid]


def close_all():
    for s in _open.values():
        s.close()
    _open.clear()


def add_group(s, name, tradition="", role="study"):
    if not name:
        raise ValueError("A group needs a name.")
    if s.one("SELECT id FROM groups WHERE name=?", (name,)):
        raise ValueError(f"A group called '{name}' already exists.")
    gid = s.ex("INSERT INTO groups(name, tradition, role) VALUES (?,?,?)", (name, tradition, role))
    s.log("group.add", name)
    return gid


def set_constants(s, new):
    info = s.info()
    if info["locked"]:
        raise PermissionError("This study's constants are locked. Create a new study to use different constants.")
    s.ex("UPDATE study SET constants=? WHERE id=1", (json.dumps(new),))
    s.log("constants.update", "")


def lock(s):
    s.ex("UPDATE study SET locked=1 WHERE id=1")
    s.log("constants.lock", hashlib.sha1(json.dumps(s.constants(), sort_keys=True).encode()).hexdigest())


# ------------------------------------------------------------------ singers
def upsert_singer(s, code, name="", voice_type="", notes=""):
    code = (code or "").strip()
    if not code:
        raise ValueError("Singer ID is required.")
    r = s.one("SELECT id FROM singers WHERE code=?", (code,))
    if r:
        s.ex("UPDATE singers SET name=?, voice_type=?, notes=? WHERE id=?", (name, voice_type, notes, r["id"]))
        return r["id"]
    return s.ex("INSERT INTO singers(code, name, voice_type, notes) VALUES (?,?,?,?)", (code, name, voice_type, notes))


# ------------------------------------------------------------------ samples
REQUIRED_META = ["tradition", "piece", "performer", "voice_type", "source", "rights"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def import_file(s, src, group_id, meta=None):
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(str(src))
    grp = s.one("SELECT * FROM groups WHERE id=?", (group_id,))
    if not grp:
        raise ValueError("Unknown group.")
    digest = sha256(src)
    dup = s.one("SELECT id, filename FROM samples WHERE sha256=?", (digest,))
    if dup:
        raise ValueError(f"This file is already in the study (sample {dup['id']}, {dup['filename']}).")
    sid = s.ex("INSERT INTO samples(group_id, filename, sha256, meta, created) VALUES (?,?,?,?,?)",
               (group_id, src.name, digest, json.dumps(meta or {}, ensure_ascii=False), time.time()))
    stored = f"{sid:04d}{src.suffix.lower()}"
    dst = s.folder / "audio" / "original" / stored
    shutil.copy2(src, dst)
    prefix = "".join(w[0] for w in (grp["name"] or "S").split())[:3].upper()
    s.ex("UPDATE samples SET stored_name=?, code=? WHERE id=?", (stored, f"{prefix}-{sid:03d}", sid))
    run_qc(s, sid)
    s.log("sample.import", {"id": sid, "file": src.name, "sha256": digest})
    return sid


def sample(s, sid):
    r = sample_row(s.one("SELECT samples.*, groups.name AS group_name, groups.role AS group_role FROM samples "
                         "JOIN groups ON groups.id = samples.group_id WHERE samples.id=?", (sid,)))
    if not r:
        raise KeyError(f"No sample {sid}")
    return r


def samples(s):
    rows = [sample_row(r) for r in s.q("SELECT samples.*, groups.name AS group_name, groups.role AS group_role FROM samples "
                                       "JOIN groups ON groups.id = samples.group_id ORDER BY samples.id")]
    for r in rows:
        missing = [k for k in REQUIRED_META if not str(r["meta"].get(k, "")).strip()]
        r["meta_missing"] = missing
        r["n_segments"] = s.one("SELECT COUNT(*) n FROM segments WHERE sample_id=?", (r["id"],))["n"]
    return rows


def update_meta(s, sid, meta):
    cur = sample(s, sid)["meta"]
    cur.update(meta or {})
    s.ex("UPDATE samples SET meta=? WHERE id=?", (json.dumps(cur, ensure_ascii=False), sid))
    if meta and "group_id" in meta:
        s.ex("UPDATE samples SET group_id=? WHERE id=?", (int(meta["group_id"]), sid))


def paths(s, sid):
    r = sample(s, sid)
    a = s.folder / "audio"
    stem_dir = a / "stems" / f"{sid:04d}"
    vocals = next(iter(sorted(stem_dir.glob("*ocals*.wav"))), None) if stem_dir.exists() else None
    instr = next(iter(sorted(stem_dir.glob("*nstrumental*.wav"))), None) if stem_dir.exists() else None
    return {"original": a / "original" / r["stored_name"], "measure": a / "measure" / f"{sid:04d}.wav",
            "guide": a / "guide" / f"{sid:04d}.wav", "stems": stem_dir, "vocals": vocals, "instrumental": instr}


def run_qc(s, sid):
    r = sample(s, sid)
    res = qc.check(paths(s, sid)["original"], s.constants(), role=r["group_role"])
    override = r["meta"].get("qc_override")
    status = override or res["status"]
    s.ex("UPDATE samples SET qc=?, qc_status=?, duration=? WHERE id=?",
         (json.dumps(res), status, res.get("info", {}).get("duration"), sid))
    if res["status"] == "reject":
        reasons = "; ".join(c["message"] for c in res["checks"] if c["status"] == "reject")
        s.log("exclusion", {"sample": sid, "reason": reasons})
    return res


def override_qc(s, sid, status, reason):
    if status not in ("pass", "flag", "reject", None):
        raise ValueError("Status must be pass, flag or reject.")
    if status and not reason:
        raise ValueError("Give a reason for the override; it is written to the exclusion log.")
    update_meta(s, sid, {"qc_override": status, "qc_override_reason": reason})
    s.ex("UPDATE samples SET qc_status=? WHERE id=?", (status or sample(s, sid)["qc"].get("status", "pending"), sid))
    s.log("qc.override", {"sample": sid, "status": status, "reason": reason})


def exclusion_log(s):
    rows = s.q("SELECT t, action, detail FROM log WHERE action IN ('exclusion','qc.override','segment.exclude') ORDER BY t")
    out = []
    for r in rows:
        try:
            d = json.loads(r["detail"])
        except Exception:
            d = {"detail": r["detail"]}
        out.append({"time": r["t"], "action": r["action"], **d})
    return out


# ------------------------------------------------------------------ preparation
def prepare_sample(s, sid, use_separation=False, progress=None):
    r = sample(s, sid)
    if r["qc_status"] == "reject":
        raise ValueError("This sample was rejected by quality control. Override QC with a reason to use it.")
    p = paths(s, sid)
    c = s.constants()
    if progress:
        progress(0.1, "Writing measurement copy")
    info = prepare.measurement_copy(p["original"], p["measure"], c)
    vocal = None
    if use_separation:
        if progress:
            progress(0.3, "Separating voice and accompaniment")
        res = separation.separate(p["measure"], p["stems"], log=s.log)
        vocal = res.get("vocals")
        s.ex("UPDATE samples SET separated=1 WHERE id=?", (sid,))
    if progress:
        progress(0.8, "Writing guide copy")
    g = prepare.guide_copy(p["measure"], p["guide"], vocal_stem=vocal)
    s.ex("UPDATE samples SET prepared=1 WHERE id=?", (sid,))
    s.log("sample.prepare", {"sample": sid, **info, "guide": g["source"], "separated": bool(vocal)})
    return {**info, **g}


def correct_drift(s, sid):
    r = sample(s, sid)
    if not r["tonic_hz"]:
        raise ValueError("Set the tonic first; drift is measured from the drone at the tonic.")
    p = paths(s, sid)
    y, sr = audio_io.read(p["measure"], mono=True)
    d = tonic.drift(y, sr, r["tonic_hz"])
    if d is None:
        raise ValueError("Recording too short to measure drift (needs at least 40 s).")
    times, ratios = d
    spread = float(1200 * np.log2(ratios.max() / ratios.min()))
    y2 = prepare.speed_correct(y, sr, times, ratios)
    audio_io.write(p["measure"], y2, sr, "FLOAT")
    prepare.guide_copy(p["measure"], p["guide"])
    s.log("sample.drift_correct", {"sample": sid, "drift_span_cents": spread})
    return {"drift_span_cents": spread, "points": len(times)}


def _need_prepared(s, sid):
    p = paths(s, sid)
    if not p["measure"].exists():
        raise ValueError("Prepare this sample first (Prepare tab).")
    return p


def measure_source(s, sid):
    """The audio values are read from: the separated vocal stem if the researcher chose it, else the measurement copy."""
    r = sample(s, sid)
    p = paths(s, sid)
    if r["meta"].get("measure_from") == "vocal stem" and p["vocals"] and Path(p["vocals"]).exists():
        return Path(p["vocals"]), "vocal stem"
    return p["measure"], "measurement copy"


# ------------------------------------------------------------------ tonic
def propose_tonic(s, sid, method=None):
    p = _need_prepared(s, sid)
    r = sample(s, sid)
    trad = (r["meta"].get("tradition") or r["group_name"] or "").lower()
    if method is None:
        method = "key" if any(w in trad for w in ("opera", "western", "classical voice", "vocalset")) else "drone"
    y, sr = audio_io.read(p["measure"], mono=True)
    yg, srg = audio_io.read(p["guide"], mono=True) if p["guide"].exists() else (y, sr)
    lim = int(sr * 180)  # first 3 minutes are enough
    _, f0 = measures.pitch_track(yg[:lim], srg, s.constants(), r["meta"].get("voice_type", ""))
    res = (tonic.propose_key if method == "key" else tonic.propose_drone)(y[:lim], sr, f0=f0, consts=s.constants())
    if res is None:
        raise ValueError("No tonic could be proposed: not enough pitched sound.")
    s.ex("UPDATE samples SET tonic_hz=?, tonic_method=?, tonic_confirmed=0 WHERE id=?", (res["hz"], res["method"], sid))
    s.log("tonic.propose", {"sample": sid, **res})
    return res


def confirm_tonic(s, sid, hz):
    hz = float(hz)
    if not 40 <= hz <= 1000:
        raise ValueError("Tonic must be between 40 and 1000 Hz.")
    s.ex("UPDATE samples SET tonic_hz=?, tonic_confirmed=1, tonic_method=COALESCE(tonic_method,'manual') WHERE id=?",
         (hz, sid))
    s.log("tonic.confirm", {"sample": sid, "hz": hz})


# ------------------------------------------------------------------ segments
def segments(s, sid=None):
    if sid:
        return s.q("SELECT segments.*, singers.code AS singer_code FROM segments LEFT JOIN singers ON singers.id="
                   "segments.singer_id WHERE sample_id=? ORDER BY start", (sid,))
    return s.q("SELECT segments.*, singers.code AS singer_code FROM segments LEFT JOIN singers ON singers.id="
               "segments.singer_id ORDER BY sample_id, start")


def add_segment(s, sid, start, end, kind="phrase", section="free", singer_code=None, vowel="", label="", notes=""):
    start, end = float(start), float(end)
    r = sample(s, sid)
    if end <= start:
        raise ValueError("Segment end must be after its start.")
    if r["duration"] and end > r["duration"] + 0.05:
        raise ValueError("Segment runs past the end of the recording.")
    if kind not in ("phrase", "vowel", "rhythm"):
        raise ValueError("Kind must be phrase, vowel or rhythm.")
    if section not in ("free", "metred"):
        raise ValueError("Section must be free or metred.")
    singer_id = None
    singer_code = singer_code or r["meta"].get("singer_id")
    if singer_code:
        row = s.one("SELECT id FROM singers WHERE code=?", (singer_code,))
        singer_id = row["id"] if row else upsert_singer(s, singer_code)
    return s.ex("INSERT INTO segments(sample_id, start, end, kind, section, singer_id, vowel, label, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?)", (sid, start, end, kind, section, singer_id, vowel, label, notes))


def update_segment(s, seg_id, **kw):
    allowed = {"start", "end", "kind", "section", "vowel", "label", "notes", "excluded"}
    if "singer_code" in kw:
        code = kw.pop("singer_code")
        sid = None
        if code:
            row = s.one("SELECT id FROM singers WHERE code=?", (code,))
            sid = row["id"] if row else upsert_singer(s, code)
        s.ex("UPDATE segments SET singer_id=? WHERE id=?", (sid, seg_id))
    for k, v in kw.items():
        if k in allowed:
            s.ex(f"UPDATE segments SET {k}=? WHERE id=?", (v, seg_id))
    if kw.get("excluded"):
        s.log("segment.exclude", {"segment": seg_id, "reason": kw.get("notes", "")})


def delete_segment(s, seg_id):
    s.ex("DELETE FROM segments WHERE id=?", (seg_id,))


def suggest_segments(s, sid):
    """Propose held vowels (steady notes) and phrases from the guide copy, for the researcher to accept or edit."""
    p = _need_prepared(s, sid)
    r = sample(s, sid)
    c = s.constants()
    y, sr = audio_io.read(p["guide"], mono=True)
    t, f0 = measures.pitch_track(y, sr, c, r["meta"].get("voice_type", ""))
    ref = r["tonic_hz"] or (np.median(f0[f0 > 0]) if (f0 > 0).any() else 100.0)
    cts = measures.cents(f0, ref)
    out = []
    for a, b in measures.stable_notes(t, cts, c["segments"]["vowel_min_s"], max_spread=c["segments"]["vowel_max_drift_cents"]):
        out.append({"start": round(float(t[a]), 3), "end": round(float(t[b - 1]), 3), "kind": "vowel"})
    voiced = f0 > 0
    # phrases: voiced regions merged across gaps shorter than 0.6 s, kept if >= 3 s, cut to <= phrase_max_s
    i, n = 0, len(t)
    regions = []
    while i < n:
        if voiced[i]:
            j = i
            gap = 0
            while j + 1 < n and (voiced[j + 1] or gap < 60):
                j += 1
                gap = 0 if voiced[j] else gap + 1
            regions.append((t[i], t[j - gap]))
            i = j + 1
        else:
            i += 1
    for a, b in regions:
        if b - a >= 3:
            mx = c["segments"]["phrase_max_s"]
            k = a
            while k < b - 2:
                out.append({"start": round(float(k), 3), "end": round(float(min(b, k + mx)), 3), "kind": "phrase"})
                k += mx
    return out


# ------------------------------------------------------------------ ornaments, rhythm
def analyse_ornaments(s, seg_id):
    seg = s.one("SELECT * FROM segments WHERE id=?", (seg_id,))
    r = sample(s, seg["sample_id"])
    src, _ = measure_source(s, r["id"])
    y, sr = audio_io.segment(src, seg["start"], seg["end"])
    ev = ornament.analyse(y, sr, s.constants(), r["meta"].get("voice_type", ""), r["tonic_hz"])
    s.ex("DELETE FROM ornaments WHERE segment_id=? AND reviewed=0", (seg_id,))
    for e in ev:
        s.ex("INSERT INTO ornaments(segment_id, start, end, rate_hz, extent_cents, regularity, auto_label, final_label) "
             "VALUES (?,?,?,?,?,?,?,?)", (seg_id, seg["start"] + e["start"], seg["start"] + e["end"], e["rate_hz"],
                                          e["extent_cents"], e["regularity"], e["auto_label"],
                                          e["auto_label"] if e["auto_label"] != "review" else None))
    return ev


def review_ornament(s, oid, label):
    if label not in ("vibrato", "ornament", "neither"):
        raise ValueError("Label must be vibrato, ornament or neither.")
    s.ex("UPDATE ornaments SET final_label=?, reviewed=1 WHERE id=?", (label, oid))


def propose_beats(s, sid, start=None, end=None):
    p = _need_prepared(s, sid)
    src = p["instrumental"] if p["instrumental"] else p["guide"]
    res = rhythm.propose_beats(src, start, end)
    s.ex("DELETE FROM cycles WHERE sample_id=? AND source='proposed'", (sid,))
    s.exmany("INSERT INTO cycles(sample_id, t, kind, source) VALUES (?,?,?,?)",
             [(sid, b, "beat", "proposed") for b in res["beats"]])
    res["source_audio"] = "percussion/accompaniment stem" if p["instrumental"] else "guide copy"
    return res


def set_marks(s, sid, times, kind="cycle"):
    """Replace the researcher's confirmed marks of one kind (cycle or beat)."""
    s.ex("DELETE FROM cycles WHERE sample_id=? AND kind=? AND source='manual'", (sid, kind))
    s.exmany("INSERT INTO cycles(sample_id, t, kind, source) VALUES (?,?,?,?)",
             [(sid, float(t), kind, "manual") for t in sorted(times)])
    s.log("rhythm.marks", {"sample": sid, "kind": kind, "n": len(times)})


def accept_proposed_beats(s, sid):
    s.ex("UPDATE cycles SET source='manual' WHERE sample_id=? AND source='proposed'", (sid,))


def marks(s, sid):
    return s.q("SELECT * FROM cycles WHERE sample_id=? ORDER BY t", (sid,))


# ------------------------------------------------------------------ analysis
def versions():
    import librosa, parselmouth, scipy, statsmodels
    v = {"sonicdiff": VERSION, "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
         "librosa": librosa.__version__, "parselmouth": parselmouth.__version__, "praat": parselmouth.PRAAT_VERSION,
         "statsmodels": statsmodels.__version__, "platform": platform.platform()}
    sep = separation.available()
    v["separation"] = sep.get("models") if sep["ok"] else "not installed"
    return v


def analyse(s, progress=None, sample_ids=None):
    """Measure every included segment of every usable sample with the locked constants."""
    info = s.info()
    if not info["locked"]:
        lock(s)
    c = s.constants()
    chash = hashlib.sha1(json.dumps(c, sort_keys=True).encode()).hexdigest()
    run = s.ex("INSERT INTO runs(started, versions, constants_hash, status) VALUES (?,?,?,?)",
               (time.time(), json.dumps(versions()), chash, "running"))
    segs = s.q("SELECT segments.*, samples.qc_status, samples.tonic_hz, samples.meta FROM segments JOIN samples ON "
               "samples.id = segments.sample_id WHERE segments.excluded=0 AND samples.qc_status != 'reject'")
    if sample_ids:
        segs = [g for g in segs if g["sample_id"] in sample_ids]
    if not segs:
        s.ex("UPDATE runs SET status='empty', finished=? WHERE id=?", (time.time(), run))
        raise ValueError("No segments to analyse. Mark segments in the Segment tab first.")
    marks_by = {}
    done, skipped = 0, []
    for i, g in enumerate(segs):
        if progress:
            progress(i / len(segs), f"Segment {i + 1} of {len(segs)}")
        try:
            sid = g["sample_id"]
            meta = json.loads(g["meta"] or "{}")
            src, _ = measure_source(s, sid)
            if not Path(src).exists():
                skipped.append({"segment": g["id"], "reason": "sample not prepared"})
                continue
            y, sr = audio_io.segment(src, g["start"], g["end"])
            if sid not in marks_by:
                m = marks(s, sid)
                marks_by[sid] = ([x["t"] for x in m if x["kind"] == "cycle" and x["source"] == "manual"],
                                 [x["t"] for x in m if x["kind"] == "beat" and x["source"] == "manual"])
            cyc, beats = marks_by[sid]
            on = None
            if g["kind"] in ("rhythm", "phrase"):
                pth = paths(s, sid)
                osrc = pth["instrumental"] if (g["kind"] == "rhythm" and pth["instrumental"]) else (
                    pth["guide"] if pth["guide"].exists() else src)
                on_abs = rhythm.onsets(osrc, g["start"], g["end"])
                on = [x - g["start"] for x in on_abs]
            in_seg = lambda arr: [x - g["start"] for x in arr if g["start"] <= x <= g["end"]]
            res = measures.measure_segment(y, sr, c, g["kind"], meta.get("voice_type", ""), g["tonic_hz"], onsets=on,
                                           cycles=in_seg(cyc) or None, beats=in_seg(beats) or None)
            s.exmany("INSERT INTO results(run_id, segment_id, feature, value, unit) VALUES (?,?,?,?,?)",
                     [(run, g["id"], k, float(v), measures.UNITS.get(k, "")) for k, v in res.items()])
            done += 1
        except Exception as e:
            skipped.append({"segment": g["id"], "reason": f"{type(e).__name__}: {e}"[:200]})
    s.ex("UPDATE runs SET status='done', finished=? WHERE id=?", (time.time(), run))
    s.log("analyse", {"run": run, "segments": done, "skipped": skipped})
    if progress:
        progress(1.0, "Done")
    return {"run": run, "segments": done, "skipped": skipped}


def latest_run(s):
    r = s.one("SELECT * FROM runs WHERE status='done' ORDER BY id DESC LIMIT 1")
    return r


def results_frame(s, run_id=None, kind=None, section=None, include_roles=("study",)):
    import pandas as pd
    run = run_id or (latest_run(s) or {}).get("id")
    if not run:
        return pd.DataFrame(columns=["group", "singer", "feature", "value"])
    sql = ("SELECT results.feature, results.value, results.unit, segments.id AS segment, segments.kind, segments.section, "
           "segments.start, segments.end, samples.id AS sample, samples.code AS sample_code, groups.name AS grp, "
           "groups.role AS role, singers.code AS singer, samples.meta FROM results "
           "JOIN segments ON segments.id = results.segment_id JOIN samples ON samples.id = segments.sample_id "
           "JOIN groups ON groups.id = samples.group_id LEFT JOIN singers ON singers.id = segments.singer_id "
           "WHERE results.run_id=?")
    df = pd.DataFrame(s.q(sql, (run,)))
    if df.empty:
        return pd.DataFrame(columns=["group", "singer", "feature", "value"])
    df = df.rename(columns={"grp": "group"})
    # a segment without a singer label counts as its own (unknown) singer per sample: never pooled across samples
    df["singer"] = df["singer"].fillna("unlabelled-" + df["sample_code"].astype(str))
    if include_roles:
        df = df[df["role"].isin(include_roles)]
    if kind:
        df = df[df["kind"] == kind]
    if section:
        df = df[df["section"] == section]
    return df


def bias_table(s):
    return {r["feature"]: r for r in s.q("SELECT * FROM bias")}


def save_bias(s, b):
    for f, v in b.items():
        s.ex("INSERT OR REPLACE INTO bias(feature, mean_shift, sd_shift, n, unit, created) VALUES (?,?,?,?,?,?)",
             (f, v["mean_shift"], v["sd_shift"], v["n"], v["unit"], time.time()))


def add_note(s, text, segment_id=None, sample_id=None, kind="musicological"):
    if not text or not text.strip():
        raise ValueError("Note is empty.")
    return s.ex("INSERT INTO notes(segment_id, sample_id, kind, text, created) VALUES (?,?,?,?,?)",
                (segment_id, sample_id, kind, text.strip(), time.time()))
