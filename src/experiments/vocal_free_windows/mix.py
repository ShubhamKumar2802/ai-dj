"""Hard-cut and short-overlap output tracks, plus the helpers the bass swap shares.

Every output is full length: A from sample 0 to the exit, then B from its entry (bar 1) to
its end. Both tracks play at their original tempo — the pair is assumed to be at about the
same BPM (design.md), so drift is reported, never corrected.
"""

import numpy as np

from render.transition_renderer import Junction, StereoPCM, render_junction

SAMPLE_RATE = 48000
CUT_ON_THE_ONE_TIER = 3


def to_sample(seconds: float) -> int:
    return round(seconds * SAMPLE_RATE)


def loudness_gain(lufs_a: float, lufs_b: float, match: bool) -> float:
    """Linear gain for all of B's audio: A's integrated LUFS minus B's, in dB."""
    return 10 ** ((lufs_a - lufs_b) / 20) if match else 1.0


def transition_span(downbeats: list[float], exit_bar: int, n_bars: int, bpm_a: float) -> float:
    """Seconds from `exit_bar`'s downbeat to `n_bars` of A's own bars later. Past A's last
    downbeat it falls back to `n_bars` bars of 4 beats at `bpm_a`."""
    start = downbeats[exit_bar - 1]
    end_index = exit_bar - 1 + n_bars
    if end_index < len(downbeats):
        return downbeats[end_index] - start
    return n_bars * 240.0 / bpm_a


def bars_left(downbeats: list[float], exit_bar: int) -> int:
    """Whole bars of A from `exit_bar`'s downbeat to its last downbeat."""
    return len(downbeats) - exit_bar


def drift_ms(span_s: float, bpm_a: float, bpm_b: float) -> float:
    """How far B's beat drifts against A's over `span_s` seconds, both at original tempo."""
    return span_s * abs(1.0 - bpm_b / bpm_a) * 1000.0


def peak_dbfs(audio: StereoPCM) -> float:
    return float(20 * np.log10(np.max(np.abs(audio.samples)) + 1e-10))


def segment(samples: np.ndarray, start: int, length: int) -> np.ndarray:
    """`length` samples from `start`, zero-padded past the end of `samples`."""
    out = samples[start : start + length]
    if len(out) < length:
        out = np.pad(out, ((0, length - len(out)), (0, 0)))
    return out


def render_cut(
    a: StereoPCM, b: StereoPCM, exit_s: float, entry_s: float, bpm_a: float
) -> StereoPCM:
    """A tier-3 hard cut on the downbeat, through the existing transition renderer."""
    junction = Junction(
        from_track="A",
        to_track="B",
        cue_out=exit_s,
        cue_in=entry_s,
        strategy_tier=CUT_ON_THE_ONE_TIER,
        ramp_bars=0,
        length_bars=0,
        bar_seconds=240.0 / bpm_a,
        rate_a=1.0,
        rate_b=1.0,
        gain_db_a=0.0,
        gain_db_b=0.0,
        envelopes=[],
    )
    return render_junction(junction, a, b)


def render_overlap(
    a: StereoPCM, b: StereoPCM, exit_s: float, entry_s: float, span_s: float
) -> StereoPCM:
    """A to the exit, then `span_s` of equal-power crossfade (A out, B in), then B to its end.
    A and B are uncorrelated, so cos/sin keeps the summed power constant."""
    exit_i, entry_i, n = to_sample(exit_s), to_sample(entry_s), to_sample(span_s)
    t = (np.arange(n, dtype=np.float32) / n)[:, None]
    blend = segment(a.samples, exit_i, n) * np.cos(t * np.pi / 2) + segment(
        b.samples, entry_i, n
    ) * np.sin(t * np.pi / 2)
    samples = np.concatenate([a.samples[:exit_i], blend, b.samples[entry_i + n :]], axis=0)
    return StereoPCM(samples=samples.astype(np.float32), sample_rate=SAMPLE_RATE)
