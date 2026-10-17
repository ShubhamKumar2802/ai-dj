"""Hard-cut audio preview of one transition, via the existing tier-3 renderer.

`cut_on_the_one` always plays A from sample 0 to `cue_out`, then B from `cue_in` to its end.
To get a short clip, the PCM is trimmed to the preview window first and the junction's cue
points are expressed relative to the trimmed audio. The LLM's suggested technique is not
rendered (decision: hard cut only).
"""

from pathlib import Path

import numpy as np

from render.playlist_renderer.writer import write_wav
from render.transition_renderer import Junction, StereoPCM, render_junction

CUT_ON_THE_ONE_TIER = 3


def trim(samples: np.ndarray, sample_rate: int, start_s: float, end_s: float) -> np.ndarray:
    """Samples between `start_s` and `end_s`, clipped to what the track has."""
    start = max(0, round(start_s * sample_rate))
    end = min(len(samples), round(end_s * sample_rate))
    return samples[start:max(start, end)]


def build_junction(
    from_track: str, to_track: str, pre_s: float, bpm_a: float
) -> Junction:
    """A straight cut: A's trimmed clip plays to its end (`pre_s`), B's from its start."""
    return Junction(
        from_track=from_track,
        to_track=to_track,
        cue_out=pre_s,
        cue_in=0.0,
        strategy_tier=CUT_ON_THE_ONE_TIER,
        ramp_bars=0,
        length_bars=0,
        bar_seconds=240.0 / bpm_a,  # 4 beats per bar at A's tempo
        rate_a=1.0,
        rate_b=1.0,
        gain_db_a=0.0,
        gain_db_b=0.0,
        envelopes=[],
    )


def render_preview(
    samples_a: np.ndarray,
    samples_b: np.ndarray,
    sample_rate: int,
    exit_time: float,
    entry_time: float,
    pre_s: float,
    post_s: float,
    from_track: str,
    to_track: str,
    bpm_a: float,
) -> StereoPCM:
    """A from `exit_time - pre_s` to `exit_time`, then B from `entry_time` to
    `entry_time + post_s`, each clipped at its track's edges."""
    clip_a = trim(samples_a, sample_rate, exit_time - pre_s, exit_time)
    clip_b = trim(samples_b, sample_rate, entry_time, entry_time + post_s)
    junction = build_junction(from_track, to_track, len(clip_a) / sample_rate, bpm_a)
    return render_junction(
        junction,
        StereoPCM(samples=clip_a, sample_rate=sample_rate),
        StereoPCM(samples=clip_b, sample_rate=sample_rate),
    )


def write_preview(audio: StereoPCM, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_wav(audio, str(path))
    return path
