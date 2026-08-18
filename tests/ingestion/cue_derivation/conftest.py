"""Shared fixture-builder helpers for ingestion/cue_derivation's tests.

This module never touches audio (spec §0) — every fixture here is a
hand-built RawFeatures/PerBarFeatures instance, JSON-constructible in
principle, never a real track (spec §11). Two factory fixtures
(make_per_bar_features, make_raw_features) expose the builder functions
below to every test file; each test calls them directly with whatever
per-field overrides that test's scenario needs.
"""

import pytest

from ingestion.feature_extractor.schema import PerBarFeatures, RawFeatures, RiserCandidate

_CHROMA_DIM = 12
_DEFAULT_CHROMA = [1.0 / _CHROMA_DIM] * _CHROMA_DIM


def _make_per_bar_features(
    n_bars: int,
    bpm: float = 130.0,
    beats_per_bar: int = 4,
    start_offset: float = 0.0,
    rms: list[float] | None = None,
    spectral_centroid: list[float] | None = None,
    spectral_flux: list[float] | None = None,
    low_band_energy: list[float] | None = None,
    high_band_energy: list[float] | None = None,
    chroma_vector: list[list[float]] | None = None,
) -> list[PerBarFeatures]:
    """n_bars of PerBarFeatures at a fixed bpm — every field defaults to a
    flat, boring value so a test only needs to override the fields it cares
    about. Per-field overrides are lists of length n_bars. start_offset
    shifts bar 0's start_time away from 0.0 — needed to model a real
    free-time intro before grid_start (e.g. to test a riser preceding it).
    """
    bar_duration = beats_per_bar * 60.0 / bpm

    def _field(values: list[float] | None, default: float) -> list[float]:
        return values if values is not None else [default] * n_bars

    rms_vals = _field(rms, 0.2)
    centroid_vals = _field(spectral_centroid, 1000.0)
    flux_vals = _field(spectral_flux, 0.1)
    low_vals = _field(low_band_energy, 0.1)
    high_vals = _field(high_band_energy, 0.1)
    chroma_vals = chroma_vector if chroma_vector is not None else [_DEFAULT_CHROMA] * n_bars

    return [
        PerBarFeatures(
            bar_index=i,
            start_time=start_offset + i * bar_duration,
            end_time=start_offset + (i + 1) * bar_duration,
            rms=rms_vals[i],
            spectral_centroid=centroid_vals[i],
            spectral_flux=flux_vals[i],
            low_band_energy=low_vals[i],
            high_band_energy=high_vals[i],
            chroma_vector=list(chroma_vals[i]),
        )
        for i in range(n_bars)
    ]


def _make_raw_features(
    per_bar_features: list[PerBarFeatures],
    bpm: float = 130.0,
    beats_per_bar: int = 4,
    downbeat_confidence: float = 0.5,
    downbeat_times: list[float] | None = None,
    energy_curve: list[float] | None = None,
    vocal_band_energy: list[float] | None = None,
    riser_candidates: list[RiserCandidate] | None = None,
) -> RawFeatures:
    """Full RawFeatures with sane, boring defaults for every field this
    module doesn't care about — a test only overrides what it's testing.
    """
    n_bars = len(per_bar_features)

    if downbeat_times is None:
        downbeat_times = [bar.start_time for bar in per_bar_features]
        if per_bar_features:
            downbeat_times.append(per_bar_features[-1].end_time)

    bar_duration = beats_per_bar * 60.0 / bpm
    beat_times = [
        i * bar_duration + k * (bar_duration / beats_per_bar)
        for i in range(n_bars)
        for k in range(beats_per_bar)
    ]

    duration = per_bar_features[-1].end_time if per_bar_features else 0.0

    return RawFeatures(
        content_hash="test-hash",
        feature_extractor_version="test",
        source_path="test.mp3",
        duration=duration,
        sample_rate=48000,
        bpm=bpm,
        bpm_confidence=0.9,
        beat_times=beat_times,
        downbeat_times=downbeat_times,
        downbeat_confidence=downbeat_confidence,
        beats_per_bar=beats_per_bar,
        per_bar_features=per_bar_features,
        lufs_integrated=-10.0,
        true_peak=-1.0,
        energy_curve=energy_curve if energy_curve is not None else [-10.0] * n_bars,
        vocal_band_energy=vocal_band_energy if vocal_band_energy is not None else [50.0] * n_bars,
        key="8A",
        key_confidence=0.8,
        riser_candidates=riser_candidates if riser_candidates is not None else [],
    )


@pytest.fixture
def make_per_bar_features():
    return _make_per_bar_features


@pytest.fixture
def make_raw_features():
    return _make_raw_features
