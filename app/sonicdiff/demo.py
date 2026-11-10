"""Demo corpus: synthetic recordings in two styles, so every tab can be tried before real data is loaded.

'Drone style' = tanpura-like drone, raga-like phrases with glides and little vibrato.
'Vibrato style' = no drone, regular wide vibrato, a strong singer's-formant cluster.
These are signals, not music; they exist to exercise and test the software.
"""
from pathlib import Path

import numpy as np

from . import audio_io, synth

SR = 48000


def make(folder, n_singers=3, seconds=14):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    files = []
    for k in range(n_singers):
        sa = [138.59, 146.83, 155.56, 130.81, 164.81][k % 5]
        drone = synth.tanpura_drone(sa, seconds + 2, SR, amp=0.06, seed=k)
        phr = synth.raga_phrase(sa, SR, swaras=(0, 200, 400, 700, 900, 700, 400, 200, 0, -500, 0),
                                note_dur=1.1 + 0.1 * k, vib_cents=8, glide=0.18, seed=k)
        held = synth.voice(sa, 2.5, SR, vib_rate=0, noise_db=26 + 3 * k, seed=10 + k,
                           formants=((650, 90), (1100, 100), (2500, 150)))
        y = np.concatenate([phr, np.zeros(SR // 3, dtype=np.float32), held])
        y = y[: seconds * SR]
        y = y + drone[: len(y)]
        y = 0.7 * y / np.max(np.abs(y))
        p = folder / f"drone_style_singer{k + 1}.wav"
        audio_io.write(p, y, SR)
        files.append({"path": p, "group": "Drone style", "singer": f"DS{k + 1}", "voice_type": "male", "tonic": sa})
    for k in range(n_singers):
        f = [220.0, 246.94, 261.63, 196.0, 293.66][k % 5]
        notes = [f, f * 1.122, f * 1.26, f * 1.498, f * 1.26, f]
        parts = [synth.voice(x, 1.2, SR, vib_rate=5.6 + 0.2 * k, vib_cents=55 + 5 * k, noise_db=34 + 2 * k, seed=20 + i,
                             formants=((600, 80), (1100, 90), (2900, 350)), tilt_db_oct=-9) for i, x in enumerate(notes)]
        held = synth.voice(f, 2.5, SR, vib_rate=5.6 + 0.2 * k, vib_cents=55 + 5 * k, noise_db=34 + 2 * k, seed=30 + k,
                           formants=((600, 80), (1100, 90), (2900, 350)), tilt_db_oct=-9)
        y = np.concatenate(parts + [np.zeros(SR // 3, dtype=np.float32), held])[: seconds * SR]
        y = 0.7 * y / np.max(np.abs(y))
        p = folder / f"vibrato_style_singer{k + 1}.wav"
        audio_io.write(p, y, SR)
        files.append({"path": p, "group": "Vibrato style", "singer": f"VS{k + 1}", "voice_type": "female", "tonic": f})
    clicks, _ = synth.click_track(96, 12, SR, accel=0.15)
    audio_io.write(folder / "test_accelerating_percussion.wav", clicks, SR)
    return files


def load_into(sid_name="Demo study", folder=None, progress=None):
    """Create a demo study, import, prepare, segment and analyse it. Returns the study id."""
    from . import service
    from .paths import DEMO, projects_dir
    folder = Path(folder or (projects_dir() / "_demo_audio"))
    files = make(folder)
    sid = service.create_study(sid_name, "Synthetic demo corpus", [{"name": "Drone style", "tradition": "demo"},
                                                                    {"name": "Vibrato style", "tradition": "demo"}])
    s = service.get(sid)
    gids = {g["name"]: g["id"] for g in s.q("SELECT * FROM groups")}
    for i, f in enumerate(files):
        if progress:
            progress(i / len(files), f"Demo sample {i + 1}")
        service.upsert_singer(s, f["singer"], voice_type=f["voice_type"])
        meta = {"tradition": f["group"], "piece": "synthetic", "performer": f["singer"], "singer_id": f["singer"],
                "voice_type": f["voice_type"], "source": "SonicDiff demo generator", "rights": "generated"}
        smp = service.import_file(s, f["path"], gids[f["group"]], meta)
        service.prepare_sample(s, smp)
        service.confirm_tonic(s, smp, f["tonic"])
        for seg in service.suggest_segments(s, smp):
            service.add_segment(s, smp, seg["start"], seg["end"], seg["kind"])
    return sid
