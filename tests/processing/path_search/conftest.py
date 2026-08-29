"""Shared fixture-builder helpers for processing/path_search's tests.

Every test here is a millisecond, no-audio, JSON-fixture test (spec §12) — hand-built
Track/Cue/PhraseBoundary/ScoredEdge instances, reusing ingestion.orchestrator.schema.Track,
ingestion.cue_derivation.schema.{Cue, PhraseBoundary} and
processing.edge_builder.schema.{ScoredEdge, ScoredEdges, CostTerms} directly, never redefined.
"""

from collections.abc import Iterable, Mapping
from typing import Any

import pytest

from common.contracts.schema import Envelope, Junction, TrackRef
from ingestion.cue_derivation.schema import Cue, CueKind, PhraseBoundary
from ingestion.orchestrator.schema import Track
from processing.edge_builder.schema import CostTerms, ScoredEdge, ScoredEdges


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


def _make_cost_terms(**overrides: float) -> CostTerms:
    base: dict[str, float] = dict(
        tempo=0.0, key=0.0, energy=0.0, vocal=0.0, cue_kind=0.0, phrase=0.0, tier_penalty=0.0
    )
    return CostTerms(**{**base, **overrides})


def _make_junction(
    from_track: str = "a",
    to_track: str = "b",
    cue_out: float = 150.0,
    cue_in: float = 8.0,
    strategy_tier: int = 3,
    ramp_bars: int = 0,
    length_bars: int = 0,
    bar_seconds: float = 2.0,
    rate_a: float = 1.0,
    rate_b: float = 1.0,
    gain_db_a: float = 0.0,
    gain_db_b: float = 0.0,
    envelopes: list[Envelope] | None = None,
) -> Junction:
    return Junction(
        from_track=from_track,
        to_track=to_track,
        cue_out=cue_out,
        cue_in=cue_in,
        strategy_tier=strategy_tier,
        ramp_bars=ramp_bars,
        length_bars=length_bars,
        bar_seconds=bar_seconds,
        rate_a=rate_a,
        rate_b=rate_b,
        gain_db_a=gain_db_a,
        gain_db_b=gain_db_b,
        envelopes=list(envelopes) if envelopes is not None else [],
    )


def _make_scored_edge(
    from_track: str,
    to_track: str,
    cost: float = 1.0,
    *,
    cue_out: float = 150.0,
    cue_in: float = 8.0,
    strategy_tier: int = 3,
    length_bars: int = 0,
    bar_seconds: float = 2.0,
    plan: Junction | None = None,
    terms: CostTerms | None = None,
) -> ScoredEdge:
    junction = plan or _make_junction(
        from_track=from_track,
        to_track=to_track,
        cue_out=cue_out,
        cue_in=cue_in,
        strategy_tier=strategy_tier,
        length_bars=length_bars,
        bar_seconds=bar_seconds,
    )
    return ScoredEdge(
        from_track=from_track,
        to_track=to_track,
        cost=cost,
        plan=junction,
        terms=terms or _make_cost_terms(),
    )


def _make_scored_edges(
    spec: Mapping[tuple[str, str], dict[str, Any]] | Iterable[ScoredEdge] | None = None,
) -> ScoredEdges:
    """Build a ScoredEdges from either a per-edge kwargs mapping or pre-built edges.

    A mapping form ``{("a", "b"): {"cost": 0.5, "cue_in": 180.0}}`` routes each value
    dict straight into ``_make_scored_edge(from, to, **kwargs)``. Any pair NOT named
    is simply absent — which is exactly how "no viable junction exists" is expressed
    (spec §1); nothing is ever synthesised for a missing key.
    """
    edges: dict[tuple[str, str], ScoredEdge] = {}
    if isinstance(spec, Mapping):
        for (from_track, to_track), kwargs in spec.items():
            edges[(from_track, to_track)] = _make_scored_edge(from_track, to_track, **kwargs)
    elif spec is not None:
        for edge in spec:
            edges[(edge.from_track, edge.to_track)] = edge
    return ScoredEdges(edges=edges)


def _fully_connected(track_ids: list[str], cost: float = 1.0, **edge_kwargs: Any) -> ScoredEdges:
    """Every ordered pair (no self-edges) at a flat cost — the dense-graph baseline
    for beam/search tests that then override specific edges."""
    return _make_scored_edges(
        {(a, b): {"cost": cost, **edge_kwargs} for a in track_ids for b in track_ids if a != b}
    )


def _make_track_ref(
    id: str = "a",
    path: str = "a.mp3",
    cue_in: float | None = None,
    cue_out: float | None = None,
    fade_out_bars: int | None = None,
    lufs_integrated: float = -10.0,
) -> TrackRef:
    return TrackRef(
        id=id,
        path=path,
        cue_in=cue_in,
        cue_out=cue_out,
        fade_out_bars=fade_out_bars,
        lufs_integrated=lufs_integrated,
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


@pytest.fixture
def make_cost_terms():
    return _make_cost_terms


@pytest.fixture
def make_junction():
    return _make_junction


@pytest.fixture
def make_scored_edge():
    return _make_scored_edge


@pytest.fixture
def make_scored_edges():
    return _make_scored_edges


@pytest.fixture
def fully_connected():
    return _fully_connected


@pytest.fixture
def make_track_ref():
    return _make_track_ref
