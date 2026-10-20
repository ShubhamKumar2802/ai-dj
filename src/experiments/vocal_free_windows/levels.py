"""Per-bar vocal level of a separated vocal stem."""

import numpy as np

from ingestion.feature_extractor.schema import PerBarFeatures


def bar_levels(stem: np.ndarray, sample_rate: int, per_bar: list[PerBarFeatures]) -> list[float]:
    """Linear RMS of the mono-summed `stem` over each bar's `[start_time, end_time)`, one value
    per bar, aligned 1:1 with `per_bar` by index. Windows are clipped to the stem's length, so
    a bar past its end reads 0.0.
    """
    mono = stem.mean(axis=1) if stem.ndim == 2 else stem
    mono = mono.astype(np.float64)

    levels = []
    for bar in per_bar:
        start = min(round(bar.start_time * sample_rate), len(mono))
        end = min(round(bar.end_time * sample_rate), len(mono))
        segment = mono[start:max(start, end)]
        levels.append(float(np.sqrt(np.mean(segment**2))) if len(segment) else 0.0)
    return levels
