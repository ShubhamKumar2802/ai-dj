"""Shared fixture-builder helpers for ingestion/orchestrator's tests.

This module never touches audio (spec §0) — every fixture here is a
hand-built RawFeatures/CueDerivationResult/Track instance, never a real
track. Three factory fixtures (make_raw_features, make_cue_derivation_result,
make_track) expose the builder functions below to every test file; each test
calls them directly with whatever per-field overrides that test's scenario
needs.
"""

import pytest

from ingestion.cue_derivation.schema import Cue, CueDerivationResult, PhraseBoundary
from ingestion.feature_extractor.schema import PerBarFeatures, RawFeatures, RiserCandidate
from ingestion.orchestrator.schema import Track


def _make_raw_features(
    content_hash: str = "test-content-hash",
    feature_extractor_version: str = "test",
    source_path: str = "source-path-not-used-by-track.mp3",
    duration: float = 180.0,
    sample_rate: int = 48000,
    bpm: float = 128.0,
    bpm_confidence: float = 0.9,
    beat_times: list[float] | None = None,
    downbeat_times: list[float] | None = None,
    downbeat_confidence: float = 0.8,
    beats_per_bar: int = 4,
    per_bar_features: list[PerBarFeatures] | None = None,
    lufs_integrated: float = -10.0,
    true_peak: float = -1.0,
    energy_curve: list[float] | None = None,
    vocal_band_energy: list[float] | None = None,
    key: str | None = "8A",
    key_confidence: float | None = 0.8,
    riser_candidates: list[RiserCandidate] | None = None,
) -> RawFeatures:
    """Full RawFeatures with sane, boring defaults for every field — a test
    only overrides what it's testing. source_path deliberately differs from
    any `path` a test passes to _assemble_track/_ingest_one, so a
    path-vs-source_path mixup is assertable.
    """
    return RawFeatures(
        content_hash=content_hash,
        feature_extractor_version=feature_extractor_version,
        source_path=source_path,
        duration=duration,
        sample_rate=sample_rate,
        bpm=bpm,
        bpm_confidence=bpm_confidence,
        beat_times=beat_times if beat_times is not None else [0.0, 0.5, 1.0, 1.5],
        downbeat_times=downbeat_times if downbeat_times is not None else [0.0, 2.0],
        downbeat_confidence=downbeat_confidence,
        beats_per_bar=beats_per_bar,
        per_bar_features=per_bar_features if per_bar_features is not None else [],
        lufs_integrated=lufs_integrated,
        true_peak=true_peak,
        energy_curve=energy_curve if energy_curve is not None else [0.5, 0.6, 0.5],
        vocal_band_energy=vocal_band_energy if vocal_band_energy is not None else [0.1, 0.2, 0.1],
        key=key,
        key_confidence=key_confidence,
        riser_candidates=riser_candidates if riser_candidates is not None else [],
    )


def _make_cue_derivation_result(
    grid_start: float = 0.0,
    grid_confidence: float = 0.9,
    free_intro_end: float = 8.0,
    phrase_length_bars: float | None = 8.0,
    phrase_grid: list[PhraseBoundary] | None = None,
    structure_template: str = "edm",
    cue_ins: list[Cue] | None = None,
    cue_outs: list[Cue] | None = None,
    status: str = "ok",
    cue_derivation_version: str = "test",
) -> CueDerivationResult:
    return CueDerivationResult(
        grid_start=grid_start,
        grid_confidence=grid_confidence,
        free_intro_end=free_intro_end,
        phrase_length_bars=phrase_length_bars,
        phrase_grid=(
            phrase_grid
            if phrase_grid is not None
            else [PhraseBoundary(position=0.0, strength=1.0, bars_since_previous=None)]
        ),
        structure_template=structure_template,
        cue_ins=cue_ins
        if cue_ins is not None
        else [Cue(position=8.0, kind="hook_in", confidence=0.9)],
        cue_outs=(
            cue_outs
            if cue_outs is not None
            else [Cue(position=160.0, kind="outro_start", confidence=0.9)]
        ),
        status=status,
        cue_derivation_version=cue_derivation_version,
    )


def _make_track(
    id: str = "test-content-hash",
    path: str = "test.mp3",
    content_hash: str = "test-content-hash",
    duration: float = 180.0,
    sample_rate: int = 48000,
    bpm: float = 128.0,
    bpm_confidence: float = 0.9,
    beat_times: list[float] | None = None,
    downbeat_times: list[float] | None = None,
    downbeat_confidence: float = 0.8,
    beats_per_bar: int = 4,
    grid_start: float = 0.0,
    grid_confidence: float = 0.9,
    free_intro_end: float = 8.0,
    phrase_length_bars: float | None = 8.0,
    phrase_grid: list[PhraseBoundary] | None = None,
    key: str | None = "8A",
    key_confidence: float | None = 0.8,
    lufs_integrated: float = -10.0,
    true_peak: float = -1.0,
    energy_curve: list[float] | None = None,
    vocal_mask: list[float] | None = None,
    structure_template: str = "edm",
    cue_ins: list[Cue] | None = None,
    cue_outs: list[Cue] | None = None,
    familiarity_score: float | None = None,
    era: str | None = None,
    is_club_edit: bool | None = None,
    analysis_version: str = "test+test",
    status: str = "ok",
) -> Track:
    return Track(
        id=id,
        path=path,
        content_hash=content_hash,
        duration=duration,
        sample_rate=sample_rate,
        bpm=bpm,
        bpm_confidence=bpm_confidence,
        beat_times=beat_times if beat_times is not None else [0.0, 0.5, 1.0, 1.5],
        downbeat_times=downbeat_times if downbeat_times is not None else [0.0, 2.0],
        downbeat_confidence=downbeat_confidence,
        beats_per_bar=beats_per_bar,
        grid_start=grid_start,
        grid_confidence=grid_confidence,
        free_intro_end=free_intro_end,
        phrase_length_bars=phrase_length_bars,
        phrase_grid=(
            phrase_grid
            if phrase_grid is not None
            else [PhraseBoundary(position=0.0, strength=1.0, bars_since_previous=None)]
        ),
        key=key,
        key_confidence=key_confidence,
        lufs_integrated=lufs_integrated,
        true_peak=true_peak,
        energy_curve=energy_curve if energy_curve is not None else [0.5, 0.6, 0.5],
        vocal_mask=vocal_mask if vocal_mask is not None else [0.1, 0.2, 0.1],
        structure_template=structure_template,
        cue_ins=cue_ins
        if cue_ins is not None
        else [Cue(position=8.0, kind="hook_in", confidence=0.9)],
        cue_outs=(
            cue_outs
            if cue_outs is not None
            else [Cue(position=160.0, kind="outro_start", confidence=0.9)]
        ),
        familiarity_score=familiarity_score,
        era=era,
        is_club_edit=is_club_edit,
        analysis_version=analysis_version,
        status=status,
    )


@pytest.fixture
def make_raw_features():
    return _make_raw_features


@pytest.fixture
def make_cue_derivation_result():
    return _make_cue_derivation_result


@pytest.fixture
def make_track():
    return _make_track
