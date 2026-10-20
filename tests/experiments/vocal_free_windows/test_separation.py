import importlib.util

import numpy as np
import pytest

from experiments.vocal_free_windows.config import SeparatorConfig

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("demucs") is None, reason="demucs not installed"
)


def test_separate_pcm_keeps_shape_and_rate():
    from experiments.vocal_free_windows.separation import separate_pcm

    sr = 48000
    rng = np.random.default_rng(0)
    samples = (0.1 * rng.standard_normal((5 * sr, 2))).astype(np.float32)
    config = SeparatorConfig(
        model="htdemucs", shifts=1, overlap=0.25, device="auto", cache_dir="unused"
    )
    stem = separate_pcm(samples, sr, config)
    assert stem.shape == samples.shape
    assert stem.dtype == np.float32
