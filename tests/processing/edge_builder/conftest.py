"""Shared fixture-builder helpers for processing/edge_builder's tests.

Every test here is a millisecond, no-audio, JSON-fixture test (spec §9) — hand-built
Track/Cue/PhraseBoundary instances, reusing ingestion.orchestrator.schema.Track and
ingestion.cue_derivation.schema.{Cue, PhraseBoundary} directly, never redefined.
"""

import pytest

from ingestion.cue_derivation.schema import Cue, CueKind, PhraseBoundary
from ingestion.orchestrator.schema import Track


def _make_cue(
    position: float = 8.0,
    kind: CueKind = "hook_in",
    confidence: float = 0.9,
) -> Cue:
    return Cue(position=position, kind=kind, confidence=confidence)


def _make_phrase_boundary(
    position: float = 0.0,
    strength: float = 1.0,
    bars_since_previous: float | None = None,
) -> PhraseBoundary:
    return PhraseBoundary(
        position=position, strength=strength, bars_since_previous=bars_since_previous
    )


def _make_track(
    id: str = "test-track",
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
        downbeat_times=downbeat_times if downbeat_times is not None else [0.0, 2.0, 4.0, 6.0],
        downbeat_confidence=downbeat_confidence,
        beats_per_bar=beats_per_bar,
        grid_start=grid_start,
        grid_confidence=grid_confidence,
        free_intro_end=free_intro_end,
        phrase_length_bars=phrase_length_bars,
        phrase_grid=phrase_grid if phrase_grid is not None else [_make_phrase_boundary()],
        key=key,
        key_confidence=key_confidence,
        lufs_integrated=lufs_integrated,
        true_peak=true_peak,
        energy_curve=energy_curve if energy_curve is not None else [0.5, 0.6, 0.5],
        vocal_mask=vocal_mask if vocal_mask is not None else [0.1, 0.2, 0.1],
        structure_template=structure_template,
        cue_ins=cue_ins if cue_ins is not None else [_make_cue(position=8.0, kind="hook_in")],
        cue_outs=(
            cue_outs if cue_outs is not None else [_make_cue(position=160.0, kind="outro_start")]
        ),
        familiarity_score=familiarity_score,
        era=era,
        is_club_edit=is_club_edit,
        analysis_version=analysis_version,
        status=status,
    )


@pytest.fixture
def make_track():
    return _make_track


@pytest.fixture
def make_cue():
    return _make_cue


@pytest.fixture
def make_phrase_boundary():
    return _make_phrase_boundary
