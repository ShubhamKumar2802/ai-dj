from dataclasses import dataclass

import numpy as np

from common.contracts.schema import Envelope, Junction

__all__ = ["StereoPCM", "Junction", "Envelope"]


@dataclass
class StereoPCM:
    """Decoded audio for the render layer.

    ``samples`` is shape ``(n_samples, 2)``, float32 (channels-last) — matching
    ``ingestion/feature_extractor/loader.py``'s own ``StereoPCM`` and
    ``soundfile``'s frame-major layout, so the real loader and the WAV writer
    need no transpose (spec §2, Amendments 2026-08-29).

    ``sample_rate`` must be 48000 (D25). It rides on the value rather than being
    assumed by callers — every function in this module asserts it.
    """

    samples: np.ndarray
    sample_rate: int
