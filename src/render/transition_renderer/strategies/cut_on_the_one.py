import numpy as np

from render.transition_renderer.fades import linear_edge_fade
from render.transition_renderer.schema import Junction, StereoPCM
from render.transition_renderer.strategies.registry import register_strategy

SAMPLE_RATE = 48000  # D25 — the module's one canonical rate


def _to_sample(seconds: float, sample_rate: int) -> int:
    """Seconds (float64, D20) to a sample index, once, at the canonical rate."""
    return round(seconds * sample_rate)


def cut_on_the_one(junction: Junction, audio_a: StereoPCM, audio_b: StereoPCM) -> StereoPCM:
    """Tier 3 — a literal splice (spec §5).

    ``length_bars == 0`` degenerates the general blend window to zero length:
    track A plays from the top of its file to ``junction.cue_out``, track B from
    ``junction.cue_in`` to its natural end (D24), butt-joined. A 5 ms linear
    fade-out on A's tail and fade-in on B's head (``fades.py``, §5.1) kill the
    seam click; the two fades never overlap, so this is not a crossfade.

    A's slice starts at sample 0 in Milestone A — the opener plays from the top;
    a non-zero opener ``cue_in`` arrives with Milestone B (spec §5, Amendments
    2026-08-29).
    """
    assert audio_a.sample_rate == audio_b.sample_rate == SAMPLE_RATE, (
        f"cut_on_the_one requires {SAMPLE_RATE} Hz PCM (D25); got "
        f"{audio_a.sample_rate} and {audio_b.sample_rate}"
    )
    sample_rate = audio_a.sample_rate

    a_slice = audio_a.samples[0 : _to_sample(junction.cue_out, sample_rate), :]
    b_slice = audio_b.samples[_to_sample(junction.cue_in, sample_rate) :, :]

    a_slice = linear_edge_fade(a_slice, sample_rate, fade_in=False)
    b_slice = linear_edge_fade(b_slice, sample_rate, fade_in=True)

    return StereoPCM(samples=np.concatenate([a_slice, b_slice], axis=0), sample_rate=sample_rate)


register_strategy(3, cut_on_the_one)
