"""Installs the optional AI pack: PyTorch (CUDA 12.8 for RTX 50-series, or CPU), audio-separator,
Beat This!, and the vocal-separation model. Run through Install-AI-Pack.bat.

Online (default): downloads everything once (about 3–4 GB with CUDA).
Offline: if an 'ai_pack' folder with wheels and models exists next to SonicDiff (made with
Make-Offline-AI-Pack.bat on any computer with internet), installs from it without internet.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
PACK = ROOT / "ai_pack"
MODELS = ROOT / "models"
TORCH = ["torch==2.7.1", "torchaudio==2.7.1"]
OTHERS = ["audio-separator[{flavour}]==0.47.0", "beat-this==1.1.0"]
MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"


def has_nvidia():
    smi = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
    try:
        out = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True,
                             text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return None


def pip(*args):
    # the constraints file keeps every core library at the version SonicDiff was tested with
    lock = ROOT / "requirements-lock.txt"
    cons = ["-c", str(lock)] if lock.exists() else []
    cmd = [PY, "-m", "pip", "install", "--no-warn-script-location", *cons, *args]
    print(">", " ".join(cmd), flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(f"pip failed ({r.returncode}). Check the internet connection and run again.")


def make_offline():
    gpu = has_nvidia()
    flavour = "gpu" if gpu else "cpu"
    PACK.mkdir(exist_ok=True)
    idx = "https://download.pytorch.org/whl/cu128" if gpu else "https://download.pytorch.org/whl/cpu"
    subprocess.run([PY, "-m", "pip", "download", "-d", str(PACK / "wheels"), "--index-url", idx,
                    "--extra-index-url", "https://pypi.org/simple", *TORCH], check=True)
    subprocess.run([PY, "-m", "pip", "download", "-d", str(PACK / "wheels"),
                    *[o.format(flavour=flavour) for o in OTHERS]], check=True)
    (PACK / "flavour.txt").write_text(flavour)
    fetch_model(PACK / "models")
    print("Offline AI pack written to", PACK)


def fetch_model(dest):
    dest.mkdir(parents=True, exist_ok=True)
    exe = Path(PY).parent / "Scripts" / "audio-separator.exe"
    cmd = [str(exe)] if exe.exists() else [PY, "-m", "audio_separator.utils.cli"]
    subprocess.run(cmd + ["--download_model_only", "-m", MODEL, "--model_file_dir", str(dest)], check=True)


def install():
    gpu = has_nvidia()
    print("NVIDIA GPU:", gpu or "none found (CPU build will be installed)", flush=True)
    if (PACK / "wheels").exists():
        flavour = (PACK / "flavour.txt").read_text().strip() if (PACK / "flavour.txt").exists() else "cpu"
        print("Installing from the offline AI pack folder", flush=True)
        pip("--no-index", "--find-links", str(PACK / "wheels"), *TORCH, *[o.format(flavour=flavour) for o in OTHERS])
        if (PACK / "models").exists():
            MODELS.mkdir(exist_ok=True)
            for f in (PACK / "models").iterdir():
                if f.is_file():
                    shutil.copy2(f, MODELS / f.name)
    else:
        idx = "https://download.pytorch.org/whl/cu128" if gpu else "https://download.pytorch.org/whl/cpu"
        pip("--index-url", idx, "--extra-index-url", "https://pypi.org/simple", *TORCH)
        pip(*[o.format(flavour="gpu" if gpu else "cpu") for o in OTHERS])
        fetch_model(MODELS)
    import importlib
    importlib.invalidate_caches()
    code = ("import torch; print('PyTorch', torch.__version__, '| CUDA available:', torch.cuda.is_available(), "
            "'|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')")
    subprocess.run([PY, "-c", code])
    print("\nAI pack installed. Restart SonicDiff; the Prepare tab will show voice separation as available.", flush=True)


if __name__ == "__main__":
    if "--make-offline" in sys.argv:
        make_offline()
    else:
        install()
