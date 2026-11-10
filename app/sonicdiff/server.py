"""Local web engine. Listens on 127.0.0.1 only."""
import json
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import APP_NAME, VERSION, audio_io, citations, constants, jobs, measures, report, selftest, separation, service, stats
from .paths import ASSETS, SETTINGS_FILE, UI_DIR, projects_dir

app = FastAPI(title=APP_NAME, version=VERSION, docs_url=None, redoc_url=None)
app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")
if ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS)), name="assets")


@app.exception_handler(Exception)
async def _err(request: Request, exc: Exception):
    code = 400 if isinstance(exc, (ValueError, PermissionError, FileNotFoundError)) else 404 if isinstance(exc, KeyError) else 500
    msg = str(exc).strip("'\"") or type(exc).__name__
    return JSONResponse({"error": msg}, status_code=code)


def S(sid):
    return service.get(sid)


# ------------------------------------------------------------------ app
@app.get("/", response_class=HTMLResponse)
def index():
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    return html.replace("{{VERSION}}", VERSION)


@app.get("/api/info")
def info():
    hw = {"device": "CPU"}
    try:
        import torch
        if torch.cuda.is_available():
            hw = {"device": "CUDA", "gpu": torch.cuda.get_device_name(0),
                  "vram_gb": round(torch.cuda.get_device_properties(0).total_memory / 2 ** 30, 1)}
    except Exception:
        pass
    return {"name": APP_NAME, "version": VERSION, "hardware": hw, "separation": separation.available(),
            "citation_styles": citations.STYLES, "projects": str(projects_dir())}


def _settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"theme": "light"}


HEARTBEAT = {"last": None}


@app.post("/api/heartbeat")
def heartbeat():
    import time as _t
    HEARTBEAT["last"] = _t.time()
    return {"ok": True}


@app.post("/api/shutdown")
def shutdown():
    import os
    import threading as _th
    import time as _t
    service.close_all()
    _th.Thread(target=lambda: (_t.sleep(0.5), os._exit(0)), daemon=True).start()
    return {"ok": True}


@app.get("/api/labels")
def labels():
    return {k: {"group": v[0], "label": v[1], "unit": measures.UNITS[k]} for k, v in measures.GROUPS.items()}


@app.post("/api/demo")
def demo_study():
    return jobs.submit("demo", "", {}, "Build demo study")


@app.get("/api/settings")
def get_settings():
    return _settings()


@app.put("/api/settings")
async def put_settings(req: Request):
    s = _settings()
    s.update(await req.json())
    try:
        SETTINGS_FILE.write_text(json.dumps(s), encoding="utf-8")
    except Exception:
        pass
    return s


@app.get("/api/jobs")
def list_jobs(study: Optional[str] = None):
    return [{k: v for k, v in j.items() if k != "trace"} for j in jobs.all_jobs(study)]


@app.get("/api/jobs/{jid}")
def job(jid: str):
    j = jobs.get(jid)
    if not j:
        raise KeyError("No such job")
    return j


# ------------------------------------------------------------------ studies
@app.get("/api/studies")
def studies():
    return service.list_studies()


@app.post("/api/studies")
async def new_study(req: Request):
    b = await req.json()
    sid = service.create_study(b.get("name", ""), b.get("description", ""), b.get("groups", []))
    return {"id": sid}


@app.get("/api/studies/{sid}")
def study(sid: str):
    s = S(sid)
    inf = s.info()
    return {"id": sid, **inf, "groups": s.q("SELECT * FROM groups ORDER BY id"),
            "singers": s.q("SELECT singers.*, (SELECT COUNT(*) FROM segments WHERE singer_id=singers.id) n_segments "
                           "FROM singers ORDER BY code"),
            "counts": {"samples": s.one("SELECT COUNT(*) n FROM samples")["n"],
                       "segments": s.one("SELECT COUNT(*) n FROM segments")["n"],
                       "runs": s.one("SELECT COUNT(*) n FROM runs WHERE status='done'")["n"]}}


@app.post("/api/studies/{sid}/groups")
async def add_group(sid: str, req: Request):
    b = await req.json()
    return {"id": service.add_group(S(sid), b.get("name"), b.get("tradition", ""), b.get("role", "study"))}


@app.delete("/api/studies/{sid}/groups/{gid}")
def del_group(sid: str, gid: int):
    s = S(sid)
    if s.one("SELECT COUNT(*) n FROM samples WHERE group_id=?", (gid,))["n"]:
        raise ValueError("This group still has samples. Move or delete them first.")
    s.ex("DELETE FROM groups WHERE id=?", (gid,))
    return {"ok": True}


@app.put("/api/studies/{sid}/constants")
async def put_constants(sid: str, req: Request):
    service.set_constants(S(sid), await req.json())
    return {"ok": True}


@app.post("/api/studies/{sid}/constants/reset")
def reset_constants(sid: str):
    service.set_constants(S(sid), constants.defaults())
    return {"ok": True}


@app.post("/api/studies/{sid}/lock")
def lock(sid: str):
    service.lock(S(sid))
    return {"ok": True}


@app.put("/api/studies/{sid}/style")
async def style(sid: str, req: Request):
    b = await req.json()
    if b.get("style") not in citations.STYLES:
        raise ValueError("Unknown citation style.")
    S(sid).ex("UPDATE study SET citation_style=? WHERE id=1", (b["style"],))
    return {"ok": True}


# ------------------------------------------------------------------ singers
@app.post("/api/studies/{sid}/singers")
async def singer(sid: str, req: Request):
    b = await req.json()
    return {"id": service.upsert_singer(S(sid), b.get("code"), b.get("name", ""), b.get("voice_type", ""), b.get("notes", ""))}


@app.delete("/api/studies/{sid}/singers/{sg}")
def del_singer(sid: str, sg: int):
    s = S(sid)
    s.ex("UPDATE segments SET singer_id=NULL WHERE singer_id=?", (sg,))
    s.ex("DELETE FROM singers WHERE id=?", (sg,))
    return {"ok": True}


# ------------------------------------------------------------------ samples
@app.post("/api/studies/{sid}/samples")
async def upload(sid: str, group_id: int = Form(...), files: List[UploadFile] = File(...), meta: str = Form("{}")):
    s = S(sid)
    try:
        m = json.loads(meta or "{}")
    except Exception:
        m = {}
    out = []
    with tempfile.TemporaryDirectory() as td:
        for f in files:
            name = Path(f.filename or "upload.wav").name
            tmp = Path(td) / name
            with open(tmp, "wb") as fh:
                shutil.copyfileobj(f.file, fh)
            try:
                new = service.import_file(s, tmp, group_id, dict(m))
                r = service.sample(s, new)
                out.append({"file": name, "id": new, "status": r["qc_status"]})
            except Exception as e:
                out.append({"file": name, "error": str(e)})
    return out


@app.post("/api/studies/{sid}/samples/import_path")
async def import_path(sid: str, req: Request):
    """Import files already on this computer (a folder or file paths), without uploading."""
    b = await req.json()
    s = S(sid)
    p = Path(b.get("path", ""))
    files = sorted(x for x in p.iterdir() if x.suffix.lower() in (".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aif", ".aiff")) \
        if p.is_dir() else [p]
    out = []
    for f in files:
        try:
            new = service.import_file(s, f, int(b["group_id"]), dict(b.get("meta", {})))
            out.append({"file": f.name, "id": new, "status": service.sample(s, new)["qc_status"]})
        except Exception as e:
            out.append({"file": f.name, "error": str(e)})
    return out


@app.get("/api/studies/{sid}/samples")
def samples(sid: str):
    return service.samples(S(sid))


@app.get("/api/studies/{sid}/samples/{smp}")
def sample(sid: str, smp: int):
    s = S(sid)
    r = service.sample(s, smp)
    p = service.paths(s, smp)
    r["files"] = {k: bool(v and Path(v).exists()) for k, v in p.items() if k != "stems"}
    r["segments"] = service.segments(s, smp)
    return r


@app.put("/api/studies/{sid}/samples/{smp}")
async def put_sample(sid: str, smp: int, req: Request):
    service.update_meta(S(sid), smp, await req.json())
    return {"ok": True}


@app.delete("/api/studies/{sid}/samples/{smp}")
def del_sample(sid: str, smp: int):
    s = S(sid)
    p = service.paths(s, smp)
    for k in ("original", "measure", "guide"):
        try:
            Path(p[k]).unlink(missing_ok=True)
        except Exception:
            pass
    shutil.rmtree(p["stems"], ignore_errors=True)
    s.ex("DELETE FROM samples WHERE id=?", (smp,))
    s.log("sample.delete", {"sample": smp})
    return {"ok": True}


@app.post("/api/studies/{sid}/samples/{smp}/qc")
def rerun_qc(sid: str, smp: int):
    return service.run_qc(S(sid), smp)


@app.post("/api/studies/{sid}/samples/{smp}/qc_override")
async def qc_override(sid: str, smp: int, req: Request):
    b = await req.json()
    service.override_qc(S(sid), smp, b.get("status"), b.get("reason", ""))
    return {"ok": True}


@app.get("/api/studies/{sid}/samples/{smp}/audio")
def audio(sid: str, smp: int, which: str = "measure"):
    s = S(sid)
    p = service.paths(s, smp)
    if which.startswith("preview"):
        # light 22.05 kHz 16-bit copy for display and playback in the browser
        base = which.split(":", 1)[1] if ":" in which else "measure"
        src = p.get(base)
        if not src or not Path(src).exists():
            src = p["measure"] if Path(p["measure"]).exists() else p["original"]
        cache = s.folder / "cache" / f"preview_{smp:04d}_{base}.wav"
        if not cache.exists() or cache.stat().st_mtime < Path(src).stat().st_mtime:
            import soxr
            y, sr = audio_io.read(src, mono=True)
            y = soxr.resample(y, sr, 22050) if sr != 22050 else y
            audio_io.write(cache, y, 22050, "PCM_16")
        return FileResponse(str(cache), media_type="audio/wav")
    path = p.get(which)
    if which == "measure" and not Path(path).exists():
        path = p["original"]
    if not path or not Path(path).exists():
        raise KeyError(f"No {which} audio for this sample")
    if Path(path).suffix.lower() not in (".wav", ".mp3", ".ogg", ".flac"):
        raise ValueError("Prepare the sample first to listen in the browser.")
    return FileResponse(str(path))


@app.get("/api/studies/{sid}/samples/{smp}/pitch")
def pitch(sid: str, smp: int, start: float = 0.0, end: Optional[float] = None):
    s = S(sid)
    r = service.sample(s, smp)
    p = service.paths(s, smp)
    src = p["guide"] if p["guide"].exists() else p["measure"]
    if not src.exists():
        raise ValueError("Prepare the sample first.")
    end = end or r["duration"] or 60
    end = min(end, start + 600)
    y, sr = audio_io.segment(src, start, end)
    t, f0 = measures.pitch_track(y, sr, s.constants(), r["meta"].get("voice_type", ""))
    step = max(1, len(t) // 4000)
    t, f0 = t[::step] + start, f0[::step]
    c = measures.cents(f0, r["tonic_hz"]) if r["tonic_hz"] else np.full_like(f0, np.nan)
    return {"t": t.round(3).tolist(), "hz": [round(float(x), 2) if x > 0 else None for x in f0],
            "cents": [round(float(x), 1) if np.isfinite(x) else None for x in c], "tonic": r["tonic_hz"]}


@app.post("/api/studies/{sid}/samples/{smp}/prepare")
async def prepare(sid: str, smp: int, req: Request):
    b = await req.json() if (await req.body()) else {}
    return jobs.submit("prepare", sid, {"sample": smp, "separate": bool(b.get("separate"))},
                       f"Prepare sample {smp}")


@app.post("/api/studies/{sid}/prepare_all")
async def prepare_all(sid: str, req: Request):
    b = await req.json() if (await req.body()) else {}
    s = S(sid)
    js = []
    for r in service.samples(s):
        if r["qc_status"] != "reject" and (b.get("force") or not r["prepared"]):
            js.append(jobs.submit("prepare", sid, {"sample": r["id"], "separate": bool(b.get("separate"))},
                                  f"Prepare {r['code']}"))
    return js


@app.post("/api/studies/{sid}/samples/{smp}/drift")
def drift(sid: str, smp: int):
    return service.correct_drift(S(sid), smp)


@app.post("/api/studies/{sid}/samples/{smp}/tonic/propose")
async def tonic_propose(sid: str, smp: int, req: Request):
    b = await req.json() if (await req.body()) else {}
    return service.propose_tonic(S(sid), smp, b.get("method"))


@app.post("/api/studies/{sid}/samples/{smp}/tonic/confirm")
async def tonic_confirm(sid: str, smp: int, req: Request):
    b = await req.json()
    service.confirm_tonic(S(sid), smp, b.get("hz"))
    return {"ok": True}


# ------------------------------------------------------------------ segments
@app.get("/api/studies/{sid}/segments")
def all_segments(sid: str, sample: Optional[int] = None):
    return service.segments(S(sid), sample)


@app.post("/api/studies/{sid}/samples/{smp}/segments")
async def add_segment(sid: str, smp: int, req: Request):
    b = await req.json()
    return {"id": service.add_segment(S(sid), smp, b["start"], b["end"], b.get("kind", "phrase"), b.get("section", "free"),
                                      b.get("singer_code"), b.get("vowel", ""), b.get("label", ""), b.get("notes", ""))}


@app.put("/api/studies/{sid}/segments/{seg}")
async def put_segment(sid: str, seg: int, req: Request):
    service.update_segment(S(sid), seg, **(await req.json()))
    return {"ok": True}


@app.delete("/api/studies/{sid}/segments/{seg}")
def del_segment(sid: str, seg: int):
    service.delete_segment(S(sid), seg)
    return {"ok": True}


@app.get("/api/studies/{sid}/samples/{smp}/suggest")
def suggest(sid: str, smp: int):
    return service.suggest_segments(S(sid), smp)


@app.post("/api/studies/{sid}/segments/{seg}/ornaments")
def ornaments(sid: str, seg: int):
    service.analyse_ornaments(S(sid), seg)
    return S(sid).q("SELECT * FROM ornaments WHERE segment_id=? ORDER BY start", (seg,))


@app.get("/api/studies/{sid}/ornaments")
def list_orn(sid: str, review_only: bool = False):
    sql = ("SELECT ornaments.*, segments.sample_id, samples.code FROM ornaments JOIN segments ON segments.id="
           "ornaments.segment_id JOIN samples ON samples.id=segments.sample_id")
    if review_only:
        sql += " WHERE ornaments.final_label IS NULL"
    return S(sid).q(sql + " ORDER BY samples.id, ornaments.start")


@app.put("/api/studies/{sid}/ornaments/{oid}")
async def review(sid: str, oid: int, req: Request):
    service.review_ornament(S(sid), oid, (await req.json()).get("label"))
    return {"ok": True}


@app.post("/api/studies/{sid}/notes")
async def note(sid: str, req: Request):
    b = await req.json()
    return {"id": service.add_note(S(sid), b.get("text"), b.get("segment_id"), b.get("sample_id"), b.get("kind", "musicological"))}


@app.get("/api/studies/{sid}/notes")
def notes(sid: str):
    return S(sid).q("SELECT * FROM notes ORDER BY id")


@app.delete("/api/studies/{sid}/notes/{nid}")
def del_note(sid: str, nid: int):
    S(sid).ex("DELETE FROM notes WHERE id=?", (nid,))
    return {"ok": True}


# ------------------------------------------------------------------ rhythm
@app.post("/api/studies/{sid}/samples/{smp}/beats")
async def beats(sid: str, smp: int, req: Request):
    b = await req.json() if (await req.body()) else {}
    return service.propose_beats(S(sid), smp, b.get("start"), b.get("end"))


@app.get("/api/studies/{sid}/samples/{smp}/marks")
def get_marks(sid: str, smp: int):
    return service.marks(S(sid), smp)


@app.put("/api/studies/{sid}/samples/{smp}/marks")
async def put_marks(sid: str, smp: int, req: Request):
    b = await req.json()
    service.set_marks(S(sid), smp, b.get("times", []), b.get("kind", "cycle"))
    return {"ok": True}


@app.post("/api/studies/{sid}/samples/{smp}/marks/accept")
def accept(sid: str, smp: int):
    service.accept_proposed_beats(S(sid), smp)
    return {"ok": True}


# ------------------------------------------------------------------ analysis, comparison, report
@app.post("/api/studies/{sid}/analyse")
def analyse(sid: str):
    return jobs.submit("analyse", sid, {}, "Analyse all segments")


@app.get("/api/studies/{sid}/runs")
def runs(sid: str):
    return S(sid).q("SELECT id, started, finished, status, constants_hash FROM runs ORDER BY id DESC")


@app.get("/api/studies/{sid}/results")
def results(sid: str, kind: Optional[str] = None, section: Optional[str] = None):
    df = service.results_frame(S(sid), kind=kind, section=section, include_roles=None)
    if df.empty:
        return []
    return json.loads(df.drop(columns=["meta"], errors="ignore").to_json(orient="records"))


@app.get("/api/studies/{sid}/compare")
def compare(sid: str, groups: Optional[str] = None, kind: Optional[str] = None, section: Optional[str] = None):
    s = S(sid)
    df = service.results_frame(s, kind=kind or None, section=section or None)
    if groups:
        df = df[df["group"].isin(groups.split(","))]
    bias = {k: {"mean_shift": v["mean_shift"], "sd_shift": v["sd_shift"]} for k, v in service.bias_table(s).items()}
    res = stats.compare(df[["group", "singer", "feature", "value"]] if not df.empty else df, bias=bias or None)
    res["labels"] = {k: {"group": v[0], "label": v[1], "unit": measures.UNITS[k]} for k, v in measures.GROUPS.items()}
    return json.loads(json.dumps(res, default=lambda o: None if isinstance(o, float) and not np.isfinite(o) else str(o)).replace("NaN", "null"))


@app.post("/api/studies/{sid}/report")
async def make_report(sid: str, req: Request):
    b = await req.json() if (await req.body()) else {}
    return jobs.submit("report", sid, {"groups": b.get("groups") or None, "style": b.get("style") or S(sid).info()["citation_style"],
                                       "kind": b.get("kind") or None, "section": b.get("section") or None}, "Build report")


@app.get("/api/studies/{sid}/reports")
def reports(sid: str):
    s = S(sid)
    out = []
    for d in sorted((s.folder / "reports").glob("report_*"), reverse=True):
        files = sorted(str(p.relative_to(d)).replace("\\", "/") for p in d.rglob("*") if p.is_file())
        out.append({"name": d.name, "files": files})
    archives = sorted(p.name for p in (s.folder / "reports").glob("study_archive_*.zip"))
    return {"reports": out, "archives": archives}


@app.get("/api/studies/{sid}/reports/{name}/{path:path}")
def report_file(sid: str, name: str, path: str):
    base = (S(sid).folder / "reports" / name).resolve()
    f = (base / path).resolve()
    if not str(f).startswith(str(base)) or not f.is_file():
        raise KeyError("File not found")
    return FileResponse(str(f), filename=f.name)


@app.get("/api/studies/{sid}/archives/{name}")
def archive_file(sid: str, name: str):
    f = (S(sid).folder / "reports" / Path(name).name)
    if not f.exists():
        raise KeyError("File not found")
    return FileResponse(str(f), filename=f.name)


@app.post("/api/studies/{sid}/archive")
def archive(sid: str):
    s = S(sid)
    with s._lock:
        s.conn.execute("PRAGMA wal_checkpoint(FULL)")
    return {"file": report.archive(s).name}


@app.get("/api/studies/{sid}/exclusions")
def exclusions(sid: str):
    return service.exclusion_log(S(sid))


@app.get("/api/studies/{sid}/log")
def log(sid: str):
    return S(sid).q("SELECT * FROM log ORDER BY id DESC LIMIT 300")


@app.get("/api/citations")
def cites(style: str = "APA 7"):
    return {"style": style, "references": citations.reference_list(style)}


@app.post("/api/studies/{sid}/bias")
async def bias(sid: str, req: Request):
    """Remix test. Body: {"pairs": [[vowel_segment_id, accompaniment_sample_id], ...]}."""
    b = await req.json()
    return jobs.submit("bias", sid, {"pairs": b.get("pairs", [])}, "Remix bias test")


@app.get("/api/studies/{sid}/bias")
def get_bias(sid: str):
    return list(service.bias_table(S(sid)).values())


@app.post("/api/selftest")
def run_selftest():
    return jobs.submit("selftest", "", {}, "Self-test")


@app.get("/api/selftest/last")
def last_selftest():
    return selftest.last()


# ------------------------------------------------------------------ job handlers
@jobs.handler("prepare")
def _prep(sid, progress, sample, separate=False):
    return service.prepare_sample(S(sid), sample, separate, progress)


@jobs.handler("analyse")
def _an(sid, progress):
    return service.analyse(S(sid), progress)


@jobs.handler("report")
def _rep(sid, progress, groups=None, style="APA 7", kind=None, section=None):
    return report.build(S(sid), groups, style, kind, section, progress)


@jobs.handler("demo")
def _demo(sid, progress):
    from . import demo
    name = "Demo study"
    existing = {x["name"] for x in service.list_studies()}
    k = 2
    while name in existing:
        name = f"Demo study {k}"
        k += 1
    return {"study": demo.load_into(name, progress=progress)}


@jobs.handler("selftest")
def _st(sid, progress):
    return selftest.run(progress)


@jobs.handler("bias")
def _bias(sid, progress, pairs):
    s = S(sid)
    import tempfile as tf
    real = []
    with tf.TemporaryDirectory() as td:
        for i, (seg_id, acc_sid) in enumerate(pairs):
            seg = s.one("SELECT * FROM segments WHERE id=?", (seg_id,))
            if not seg or seg["kind"] != "vowel":
                raise ValueError(f"Segment {seg_id} is not a held-vowel segment.")
            src, _ = service.measure_source(s, seg["sample_id"])
            y, sr = audio_io.segment(src, seg["start"], seg["end"])
            vp = Path(td) / f"v{i}.wav"
            audio_io.write(vp, y, sr, "FLOAT")
            real.append((vp, service.paths(s, acc_sid)["measure"]))
            progress(i / max(1, len(pairs)), f"Pair {i + 1}")
        b = separation.remix_bias(real, s.constants(), log=s.log)
    service.save_bias(s, b)
    return {"features": len(b)}
