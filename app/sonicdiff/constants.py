"""Measurement constants (from 'Sample Constants — Cross-Tradition Vocal Analysis').

A study copies these defaults when created. Once the study is locked the
copy can no longer be changed, so every result in it uses the same values.
"""
import copy

DEFAULTS = {
    "audio": {
        "sample_rate": 48000,
        "highpass_hz": 60.0,
        "peak_limit_dbfs": -1.0,
        "noise_floor_limit_dbfs": -60.0,
        "min_snr_db": 30.0,
        "lossy_min_kbps": 320,
        "timbre_lufs": -23.0,
    },
    "segments": {
        "phrase_min_s": 10.0,
        "phrase_max_s": 30.0,
        "vowel_min_s": 1.0,
        "vowel_core_fraction": 0.8,
        "vowel_max_drift_cents": 50.0,
        "rhythm_min_cycles": 4,
    },
    "pitch": {
        "time_step_s": 0.01,
        "floor_male_hz": 70.0,
        "ceiling_male_hz": 700.0,
        "floor_female_hz": 100.0,
        "ceiling_female_hz": 1200.0,
        "accuracy_band_cents": 20.0,
    },
    "vibrato": {"min_note_s": 0.5, "rate_min_hz": 3.0, "rate_max_hz": 9.0},
    "loudness": {"window_s": 0.04, "hop_s": 0.01},
    "formant": {
        "n_formants": 5,
        "max_formant_male_hz": 5000.0,
        "max_formant_female_hz": 5500.0,
        "window_s": 0.025,
    },
    "spectral": {"n_fft": 2048, "hop": 480, "n_mfcc": 13, "n_mels": 40, "ltas_bandwidth_hz": 100.0},
    "hnr": {"time_step_s": 0.01, "min_pitch_hz": 75.0, "silence_threshold": 0.1, "periods_per_window": 1.0},
    "cpps": {
        "time_step_s": 0.002,
        "max_frequency_hz": 5000.0,
        "pre_emphasis_hz": 50.0,
        "time_smoothing_s": 0.01,
        "quefrency_smoothing_s": 0.001,
    },
    "perturbation": {
        "period_floor_s": 0.0001,
        "period_ceiling_s": 0.02,
        "max_period_factor": 1.3,
        "max_amplitude_factor": 1.6,
    },
    "envelope": {"attack_lo": 0.1, "attack_hi": 0.9},
    "rhythm": {"hop_s": 0.01},
}


def defaults():
    return copy.deepcopy(DEFAULTS)


def pitch_range(c, voice_type):
    p = c["pitch"]
    if str(voice_type).lower().startswith("f"):
        return p["floor_female_hz"], p["ceiling_female_hz"]
    if str(voice_type).lower().startswith("m"):
        return p["floor_male_hz"], p["ceiling_male_hz"]
    return p["floor_male_hz"], p["ceiling_female_hz"]


def max_formant(c, voice_type):
    f = c["formant"]
    return f["max_formant_female_hz"] if str(voice_type).lower().startswith("f") else f["max_formant_male_hz"]
