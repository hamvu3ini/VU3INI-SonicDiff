"""VU3INI SonicDiff launcher.

    python run.py            desktop window (falls back to the web browser)
    python run.py --browser  open in the default web browser
    python run.py --server   engine only (no window), e.g. for tests
"""
import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
sys.path.insert(0, str(APP))
os.environ["PATH"] = str(ROOT / "bin") + os.pathsep + os.environ.get("PATH", "")
os.environ.setdefault("NUMBA_CACHE_DIR", str(ROOT / "cache" / "numba"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "cache" / "matplotlib"))
os.environ.setdefault("TORCH_HOME", str(ROOT / "models" / "torch"))
os.environ.setdefault("HF_HOME", str(ROOT / "models" / "huggingface"))

LOGDIR = ROOT / "logs"
LOGDIR.mkdir(exist_ok=True)
logging.basicConfig(filename=LOGDIR / "sonicdiff.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sonicdiff")
if sys.stdout is None:  # pythonw: no console
    sys.stdout = open(LOGDIR / "stdout.log", "a", encoding="utf-8")
    sys.stderr = open(LOGDIR / "stderr.log", "a", encoding="utf-8")

PREFERRED_PORT = 8765


def running_instance(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/info", timeout=1.5) as r:
            return json.loads(r.read()).get("name", "").endswith("SonicDiff")
    except Exception:
        return False


def free_port(preferred):
    for p in [preferred] + list(range(preferred + 1, preferred + 40)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(port):
    import uvicorn
    from sonicdiff import jobs
    from sonicdiff.server import app
    jobs.start()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False, log_config=None)
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True, name="sonicdiff-server")
    t.start()
    for _ in range(300):
        if server.started:
            break
        time.sleep(0.1)
    return server, t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--server", action="store_true")
    ap.add_argument("--port", type=int, default=PREFERRED_PORT)
    a = ap.parse_args()

    if running_instance(a.port) and not a.server:
        url = f"http://127.0.0.1:{a.port}/"
        log.info("Already running; opening %s", url)
        import webbrowser
        webbrowser.open(url)
        return

    port = free_port(a.port)
    url = f"http://127.0.0.1:{port}/"
    log.info("Starting SonicDiff on %s", url)
    server, thread = serve(port)
    print(f"VU3INI SonicDiff is running at {url}", flush=True)

    if a.server:
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        return

    if not a.browser:
        try:
            import webview
            webview.create_window("VU3INI SonicDiff", url, width=1440, height=920, min_size=(1000, 680))
            webview.start()
            server.should_exit = True
            return
        except Exception as e:  # no WebView2 runtime, etc.
            log.warning("Desktop window unavailable (%s); using the web browser.", e)

    import webbrowser
    webbrowser.open(url)
    print("SonicDiff is open in your browser. It stops by itself a few minutes after the last browser tab "
          "is closed, or use Settings > Stop SonicDiff.", flush=True)
    from sonicdiff import jobs
    from sonicdiff.server import HEARTBEAT
    started = time.time()
    try:
        while thread.is_alive():
            time.sleep(2)
            last = HEARTBEAT["last"]
            busy = any(j["status"] in ("queued", "running") for j in jobs.all_jobs())
            idle_since = last or started
            if not busy and time.time() - idle_since > (180 if last else 600):
                log.info("No browser tab for a while; stopping.")
                break
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
