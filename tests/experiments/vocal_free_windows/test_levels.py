import numpy as np

from experiments.vocal_free_windows.levels import bar_levels
from ingestion.feature_extractor.schema import PerBarFeatures

SR = 1000


def _bars(n: int, bar_s: float = 2.0) -> list[PerBarFeatures]:
    return [
        PerBarFeatures(i, i * bar_s, (i + 1) * bar_s, 0.0, 0.0, 0.0, 0.0, 0.0, [])
        for i in range(n)
    ]


def test_silent_stem_gives_zeros_one_per_bar():
    bars = _bars(149)
    stem = np.zeros((149 * 2 * SR, 2), dtype=np.float32)
    levels = bar_levels(stem, SR, bars)
    assert levels == [0.0] * 149


def test_sung_bar_reads_higher_than_neighbours():
    bars = _bars(3)
    stem = np.zeros((6 * SR, 2), dtype=np.float32)
    t = np.arange(2 * SR) / SR
    stem[2 * SR : 4 * SR, :] = (0.5 * np.sin(2 * np.pi * 220 * t))[:, None]
    levels = bar_levels(stem, SR, bars)
    assert levels[0] == 0.0 and levels[2] == 0.0
    assert abs(levels[1] - 0.5 / np.sqrt(2)) < 1e-3


def test_bar_past_stem_end_reads_zero():
    levels = bar_levels(np.ones((2 * SR, 2), dtype=np.float32), SR, _bars(2))
    assert levels[0] > 0.9
    assert levels[1] == 0.0
