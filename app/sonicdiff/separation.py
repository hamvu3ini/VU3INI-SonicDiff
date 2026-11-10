"""Voice / accompaniment separation (Phase 3) and the remix bias test.

Separation uses the optional AI pack (audio-separator with UVR models,
PyTorch). The core app runs without it; the Prepare tab then says so and
offers the solo-passage route. Models are read from the app's models folder
so no download is needed at run time.
"""
import json
import time
from pathlib import Path

import numpy as np

from . import audio_io, measures
from .paths import MODELS

VOCAL_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
FALLBACK_MODEL = "UVR-MDX-NET-Voc_FT.onnx"


def available():
    try:
        import audio_separator  # noqa: F401
    except Exception as e:
        return {"ok": False, "reason": "AI pack not installed (audio-separator / PyTorch). Run Install-AI-Pack.bat.",
                "detail": str(e)[:200]}
    models = [p.name for p in MODELS.glob("*") if p.suffix in (".ckpt", ".onnx", ".pth", ".th")] if MODELS.exists() else []
    if not models:
        return {"ok": False, "reason": "No separation model found in the models folder."}
    dev = "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            dev = "cuda:" + torch.cuda.get_device_name(0)
    except Exception:
        pass
    return {"ok": True, "models": models, "device": dev}


def separate(src, out_dir, model=None, log=None):
    """Return {'vocals': path, 'instrumental': path}. Chunked so 8 GB of VRAM is enough."""
    from audio_separator.separator import Separator
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    av = available()
    if not av["ok"]:
        raise RuntimeError(av["reason"])
    model = model or (VOCAL_MODEL if VOCAL_MODEL in av["models"] else
                      FALLBACK_MODEL if FALLBACK_MODEL in av["models"] else av["models"][0])
    sep = Separator(output_dir=str(out_dir), model_file_dir=str(MODELS), output_format="WAV",
                    sample_rate=48000, use_autocast=False,
                    mdxc_params={"segment_size": 256, "override_model_segment_size": False, "batch_size": 1,
                                 "overlap": 8, "pitch_shift": 0})
    sep.load_model(model_filename=model)
    files = sep.separate(str(src))
    res = {}
    for f in files:
        p = out_dir / Path(f).name
        low = p.name.lower()
        if "vocal" in low and "instrument" not in low and "no_vocal" not in low:
            res["vocals"] = str(p)
        else:
            res["instrumental"] = str(p)
    if log:
        log("separation", {"model": model, "device": av["device"], "outputs": res})
    res["model"] = model
    return res


def remix_bias(pairs, consts, voice_type="", log=None):
    """Remix test: clean solo voice + accompaniment -> separate -> measure both.

    pairs: list of (clean_vowel_path, accompaniment_path). Returns per-feature mean and SD
    of (separated - clean), the error bar SonicDiff prints beside every separated value.
    """
    import tempfile
    shifts = {}
    for clean_p, acc_p in pairs:
        y, sr = audio_io.read(clean_p, mono=True)
        a, sra = audio_io.read(acc_p, mono=True)
        if sra != sr:
            import soxr
            a = soxr.resample(a, sra, sr)
        a = np.resize(a, len(y))
        mix = y + a * (np.sqrt(np.mean(y ** 2)) / (np.sqrt(np.mean(a ** 2)) + 1e-12))
        with tempfile.TemporaryDirectory() as td:
            mp = Path(td) / "mix.wav"
            audio_io.write(mp, mix / max(1.0, np.max(np.abs(mix)) / 0.9), sr, "FLOAT")
            out = separate(mp, td)
            ys, srs = audio_io.read(out["vocals"], mono=True)
        ref = measures.measure_segment(y, sr, consts, "vowel", voice_type)
        sep = measures.measure_segment(ys, srs, consts, "vowel", voice_type)
        for k in ref:
            if k in sep:
                shifts.setdefault(k, []).append(sep[k] - ref[k])
    out = {k: {"mean_shift": float(np.mean(v)), "sd_shift": float(np.std(v)), "n": len(v),
               "unit": measures.UNITS.get(k, "")} for k, v in shifts.items()}
    if log:
        log("remix_bias", {"pairs": len(pairs), "features": len(out)})
    return out
