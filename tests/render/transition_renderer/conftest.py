"""Synthetic fixtures for transition_renderer's tests — generated tones, no
real ``music/`` audio (spec §7). Reuses ``common.contracts.schema.Junction`` and
``render.transition_renderer.schema.StereoPCM`` directly, never redefined.
"""

import numpy as np
import pytest

from common.contracts.schema import Junction
from render.transition_renderer.schema import StereoPCM

SAMPLE_RATE = 48000


def _make_pcm(
    duration_s: float = 2.0,
    *,
    value: float | None = None,
    freq: float = 220.0,
    amplitude: float = 0.5,
    sample_rate: int = SAMPLE_RATE,
) -> StereoPCM:
    """A ``(n_samples, 2)`` float32 buffer. ``value`` (constant) makes
    sample-exact assertions easy; otherwise a sine at ``freq``."""
    n = int(round(duration_s * sample_rate))
    if value is not None:
        samples = np.full((n, 2), value, dtype=np.float32)
    else:
        t = np.arange(n) / sample_rate
        wave = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        samples = np.stack([wave, wave], axis=1)
    return StereoPCM(samples=samples, sample_rate=sample_rate)


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


@pytest.fixture
def make_pcm():
    return _make_pcm


@pytest.fixture
def make_junction():
    return _make_junction
