"""DJ-style bass swap over an even number of A's bars, starting at the exit downbeat.

Each track's span is split at `crossover_hz` into `low` and `rest = signal - low`, so the
two bands sum back to the original exactly. Gains over the span (design.md):

- first half: A full; B's rest fades in (equal power), B's low muted
- halfway downbeat: A's low out, B's low in — a hard step with a 5 ms ramp
- second half: B full; A's rest fades out (equal power) to silence
"""

import numpy as np
from scipy.signal import butter, sosfiltfilt

from experiments.vocal_free_windows.mix import SAMPLE_RATE, bars_left, segment, to_sample
from render.transition_renderer import StereoPCM

FILTER_ORDER = 4
STEP_RAMP_MS = 5


def split_low(samples: np.ndarray, crossover_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """`(low, rest)` of `(n, 2)` samples. Zero-phase, so the bands stay in time."""
    sos = butter(FILTER_ORDER, crossover_hz, btype="lowpass", fs=SAMPLE_RATE, output="sos")
    low = sosfiltfilt(sos, samples.astype(np.float64), axis=0)
    return low, samples - low


def skip_reason(downbeats_a: list[float], exit_bar: int, bass_swap_bars: int) -> str | None:
    """Why the bass swap can't be rendered from `exit_bar`, or None if it can."""
    left = bars_left(downbeats_a, exit_bar)
    if left < bass_swap_bars:
        return (
            f"track A has only {left} bars after the exit at bar {exit_bar}, "
            f"fewer than the {bass_swap_bars}-bar bass swap"
        )
    return None


def gain_curves(n: int, swap: int) -> dict[str, np.ndarray]:
    """Per-sample gains for the four bands over an `n`-sample span with the bass step at
    sample `swap`."""
    i = np.arange(n, dtype=np.float64)
    ramp = max(1, round(STEP_RAMP_MS / 1000 * SAMPLE_RATE))
    step = np.clip((i - swap) / ramp, 0.0, 1.0)  # 0 before the swap downbeat, 1 after 5 ms

    first = np.clip(i / max(swap, 1), 0.0, 1.0)
    second = np.clip((i - swap) / max(n - swap, 1), 0.0, 1.0)
    return {
        "a_low": 1.0 - step,
        "b_low": step,
        "a_rest": np.where(i < swap, 1.0, np.cos(second * np.pi / 2)),
        "b_rest": np.where(i < swap, np.sin(first * np.pi / 2), 1.0),
    }


def render_bass_swap(
    a: StereoPCM,
    b: StereoPCM,
    exit_s: float,
    entry_s: float,
    span_s: float,
    swap_offset_s: float,
    crossover_hz: float,
) -> StereoPCM:
    """A to the exit, the bass swap over `span_s` (bass step `swap_offset_s` in), then B to
    its end. Same total length as the cut and overlap outputs."""
    exit_i, entry_i, n = to_sample(exit_s), to_sample(entry_s), to_sample(span_s)
    swap = to_sample(swap_offset_s)

    a_low, a_rest = split_low(segment(a.samples, exit_i, n), crossover_hz)
    b_low, b_rest = split_low(segment(b.samples, entry_i, n), crossover_hz)
    g = {k: v[:, None] for k, v in gain_curves(n, swap).items()}
    blend = a_low * g["a_low"] + a_rest * g["a_rest"] + b_low * g["b_low"] + b_rest * g["b_rest"]

    samples = np.concatenate(
        [a.samples[:exit_i], blend.astype(np.float32), b.samples[entry_i + n :]], axis=0
    )
    return StereoPCM(samples=samples.astype(np.float32), sample_rate=SAMPLE_RATE)
