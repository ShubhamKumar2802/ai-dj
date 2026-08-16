from dataclasses import dataclass

import essentia.standard as es
import numpy as np

CANONICAL_SAMPLE_RATE = 48000


@dataclass
class StereoPCM:
    """Decoded audio, always 2 channels. Not part of the public schema (§2) —
    an internal type shared between this file and its sibling modules
    (rhythm.py, spectral_features.py, loudness.py, vocal_band.py,
    key_estimation.py, riser_detection.py), all of which take it as input.
    """

    samples: np.ndarray  # shape (n_samples, 2), float32
    sample_rate: int


def load_canonical(path: str, sample_rate: int = CANONICAL_SAMPLE_RATE) -> StereoPCM:
    """Decode `path` to 48kHz float32 stereo PCM, pinned at ingestion (D25).

    This is the only file in the module allowed to import an audio decoder
    (spec §3). Essentia's `AudioLoader` preserves the file's actual channel
    count and loads at its native sample rate, but — unlike `MonoLoader` —
    has no `sampleRate` parameter to resample to. `MonoLoader` does resample,
    but also downmixes; using it here would collapse real stereo content to
    mono before "upcasting" it back, which is not what D25's mono-upcast
    rule is for (that rule is about genuinely mono *sources*, not throwing
    away stereo content this loader already has). So: load at native rate
    via `AudioLoader`, then resample explicitly per channel with Essentia's
    `Resample` algorithm.
    """
    audio, native_rate, n_channels, _md5, _bit_rate, _codec = es.AudioLoader(filename=path)()

    if n_channels == 1 or audio.shape[1] == 1:
        mono = audio[:, 0] if audio.ndim == 2 else audio
        audio = np.stack([mono, mono], axis=1)

    if native_rate != sample_rate:
        resampler = es.Resample(inputSampleRate=native_rate, outputSampleRate=sample_rate)
        left = resampler(np.ascontiguousarray(audio[:, 0], dtype=np.float32))
        right = resampler(np.ascontiguousarray(audio[:, 1], dtype=np.float32))
        n = min(len(left), len(right))
        audio = np.stack([left[:n], right[:n]], axis=1)

    return StereoPCM(samples=audio.astype(np.float32), sample_rate=sample_rate)
