"""Synthetic fixtures for playlist_renderer's tests — generated ``StereoPCM``,
a fake ``load_audio``, and a hand-built ``MixPlan`` (spec §6). Reuses
``common.contracts.schema`` and ``render.transition_renderer.schema.StereoPCM``
directly, never redefined.
"""

from collections.abc import Callable, Mapping

import numpy as np
import pytest

from common.contracts.schema import Junction, MixPlan, MixPlanConfig, TrackRef
from render.transition_renderer.schema import StereoPCM

SAMPLE_RATE = 48000


def _make_pcm(
    duration_s: float = 2.0, value: float = 0.4, sample_rate: int = SAMPLE_RATE
) -> StereoPCM:
    n = int(round(duration_s * sample_rate))
    return StereoPCM(samples=np.full((n, 2), value, dtype=np.float32), sample_rate=sample_rate)


def _make_track_ref(
    id: str = "a",
    path: str | None = None,
    cue_in: float | None = None,
    cue_out: float | None = None,
    fade_out_bars: int | None = None,
    lufs_integrated: float = -10.0,
) -> TrackRef:
    return TrackRef(
        id=id,
        path=path if path is not None else f"{id}.mp3",
        cue_in=cue_in,
        cue_out=cue_out,
        fade_out_bars=fade_out_bars,
        lufs_integrated=lufs_integrated,
    )


def _make_junction(
    from_track: str = "a",
    to_track: str = "b",
    cue_out: float = 1.0,
    cue_in: float = 0.2,
    strategy_tier: int = 3,
) -> Junction:
    return Junction(
        from_track=from_track,
        to_track=to_track,
        cue_out=cue_out,
        cue_in=cue_in,
        strategy_tier=strategy_tier,
        ramp_bars=0,
        length_bars=0,
        bar_seconds=2.0,
        rate_a=1.0,
        rate_b=1.0,
        gain_db_a=0.0,
        gain_db_b=0.0,
        envelopes=[],
    )


def _make_mix_plan(track_ids: tuple[str, ...] = ("a", "b")) -> MixPlan:
    tracks = [_make_track_ref(id=tid) for tid in track_ids]
    junctions = [
        _make_junction(from_track=track_ids[i], to_track=track_ids[i + 1])
        for i in range(len(track_ids) - 1)
    ]
    config = MixPlanConfig(
        track_count=len(track_ids),
        energy_arc="arc",
        seed_track=None,
        path_search={},
        edge_builder=None,
    )
    return MixPlan(config=config, tracks=tracks, junctions=junctions)


def _fake_load_audio(mapping: Mapping[str, StereoPCM]) -> Callable[[str], StereoPCM]:
    def _load(path: str) -> StereoPCM:
        return mapping[path]

    return _load


@pytest.fixture
def make_pcm():
    return _make_pcm


@pytest.fixture
def make_track_ref():
    return _make_track_ref


@pytest.fixture
def make_mix_plan():
    return _make_mix_plan


@pytest.fixture
def fake_load_audio():
    return _fake_load_audio
