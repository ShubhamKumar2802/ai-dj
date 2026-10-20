"""Vocal stem separation with Demucs — the only module that imports `demucs`/`torch`.

The imports live inside the functions so the rest of the experiment (and its tests) import
without the separation library. Audio goes 48 kHz -> the model's rate -> back to 48 kHz, so
the stem lines up sample-for-sample with the feature extractor's bar times (design.md).
"""

import numpy as np

from experiments.vocal_free_windows.config import SeparatorConfig
from experiments.vocal_free_windows.stem_cache import STEM_SAMPLE_RATE

VOCALS = "vocals"


def _device(choice: str) -> str:
    import torch

    if choice == "auto":
        return "mps" if torch.backends.mps.is_available() else "cpu"
    return choice


def separate_pcm(samples: np.ndarray, sample_rate: int, config: SeparatorConfig) -> np.ndarray:
    """The `(n_samples, 2)` vocal stem of `(n_samples, 2)` stereo `samples`, at `sample_rate`."""
    import julius
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    model = get_model(config.model)
    model.eval()

    wav = torch.from_numpy(np.ascontiguousarray(samples.T, dtype=np.float32))
    if sample_rate != model.samplerate:
        wav = julius.resample_frac(wav, sample_rate, model.samplerate)

    # Demucs' own CLI normalisation: separate a zero-mean, unit-std mix, then undo it.
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        sources = apply_model(
            model,
            ((wav - mean) / std)[None],
            shifts=config.shifts,
            split=True,
            overlap=config.overlap,
            device=_device(config.device),
        )[0]
    vocals = sources[model.sources.index(VOCALS)].cpu() * std + mean

    if sample_rate != model.samplerate:
        vocals = julius.resample_frac(vocals, model.samplerate, sample_rate)

    # Resampling can be off by a sample or two; pad/trim to the input length.
    n = samples.shape[0]
    out = vocals.numpy().T[:n]
    if out.shape[0] < n:
        out = np.pad(out, ((0, n - out.shape[0]), (0, 0)))
    return out.astype(np.float32)


def separate_file(path: str, config: SeparatorConfig) -> np.ndarray:
    """The 48 kHz vocal stem of the audio file at `path` (the stem cache's `Separate`)."""
    from ingestion.feature_extractor.loader import load_canonical

    pcm = load_canonical(path, STEM_SAMPLE_RATE)
    return separate_pcm(pcm.samples, pcm.sample_rate, config)
