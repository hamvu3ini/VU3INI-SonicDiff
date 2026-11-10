"""Background job queue. Long tasks (preparation, separation, analysis, reports) run one at a time.

The queue is saved to disk, so jobs interrupted by a crash or by closing the
app are run again from the start of the interrupted step on next launch.
"""
import json
import queue
import threading
import time
import traceback
import uuid

from .paths import projects_dir

_q = queue.Queue()
_jobs = {}
_lock = threading.Lock()
_handlers = {}
_started = False


def _file():
    return projects_dir() / "_jobs.json"


def _save():
    with _lock:
        keep = {k: v for k, v in _jobs.items() if v["status"] in ("queued", "running") or time.time() - v["created"] < 86400}
        try:
            _file().write_text(json.dumps(keep, default=str), encoding="utf-8")
        except Exception:
            pass


def handler(kind):
    def deco(fn):
        _handlers[kind] = fn
        return fn
    return deco


def submit(kind, study, args=None, label=""):
    jid = uuid.uuid4().hex[:10]
    j = {"id": jid, "kind": kind, "study": study, "args": args or {}, "label": label or kind, "status": "queued",
         "progress": 0.0, "message": "Waiting", "result": None, "error": None, "created": time.time()}
    with _lock:
        _jobs[jid] = j
    _save()
    _q.put(jid)
    return j


def get(jid):
    return _jobs.get(jid)


def all_jobs(study=None):
    with _lock:
        js = list(_jobs.values())
    if study:
        js = [j for j in js if j["study"] == study]
    return sorted(js, key=lambda j: -j["created"])


def _worker():
    while True:
        jid = _q.get()
        j = _jobs.get(jid)
        if not j or j["status"] not in ("queued", "running"):
            continue
        j["status"] = "running"
        j["started"] = time.time()
        _save()

        def progress(frac, msg=""):
            j["progress"] = round(float(frac), 3)
            if msg:
                j["message"] = msg

        try:
            fn = _handlers[j["kind"]]
            j["result"] = fn(j["study"], progress=progress, **j["args"])
            j["status"] = "done"
            j["progress"] = 1.0
            j["message"] = "Finished"
        except Exception as e:
            j["status"] = "error"
            j["error"] = str(e) or type(e).__name__
            j["trace"] = traceback.format_exc()[-2000:]
            j["message"] = "Failed: " + j["error"]
        j["finished"] = time.time()
        _save()


def start():
    global _started
    if _started:
        return
    _started = True
    try:
        old = json.loads(_file().read_text(encoding="utf-8"))
        for jid, j in old.items():
            if j["status"] in ("queued", "running"):
                j["status"] = "queued"
                j["message"] = "Resumed after restart"
                _jobs[jid] = j
                _q.put(jid)
            else:
                _jobs[jid] = j
    except Exception:
        pass
    threading.Thread(target=_worker, daemon=True, name="sonicdiff-jobs").start()
