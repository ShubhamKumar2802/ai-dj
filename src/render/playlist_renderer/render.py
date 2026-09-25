from typing import Callable

import numpy as np

from common.contracts.schema import MixPlan
from render.transition_renderer import linear_edge_fade
from render.transition_renderer.schema import StereoPCM

SAMPLE_RATE = 48000  # D25 — the module's one canonical rate


def _to_sample(seconds: float, sample_rate: int) -> int:
    """Seconds (float64, D20) to a sample index, once, at the canonical rate."""
    return round(seconds * sample_rate)


def _natural_end(audio: StereoPCM) -> float:
    return audio.samples.shape[0] / audio.sample_rate


def equal_power_fade_to_silence(
    segment: np.ndarray, sample_rate: int, duration_seconds: float
) -> np.ndarray:
    """Ramp the last ``duration_seconds`` of a ``(n_samples, 2)`` segment to
    silence with an equal-power (quarter-cosine) curve — spec §3/§9 Q3's
    resolution of D24's closer fallback. Returns a copy; the input is not
    mutated. Distinct from ``transition_renderer.linear_edge_fade``: that's
    5ms anti-click hygiene at a splice; this is a musically-scaled closer
    fade whose duration comes from ``TrackRef.fade_out_bars``, an already-
    decided value this module executes rather than picks (§0)."""
    n_fade = min(round(duration_seconds * sample_rate), len(segment))
    if n_fade == 0:
        return segment.copy()
    t = np.linspace(0.0, 1.0, n_fade, dtype=segment.dtype)
    ramp = np.cos(t * np.pi / 2)  # 1.0 -> 0.0
    out = segment.copy()
    out[-n_fade:] *= ramp[:, None]
    return out


def render_mix(mix_plan: MixPlan, load_audio: Callable[[str], StereoPCM]) -> StereoPCM:
    """Assemble a ``MixPlan`` into one rendered ``StereoPCM`` (spec §3,
    Milestone B — 2026-09-17 amendment).

    Every track gets exactly one body window, bounded by its flanking
    junctions (or, at the two open ends, D24's relaxed ``TrackRef`` fields).
    Interior tracks get both a fade-in (they were just cut into) and a
    fade-out (they're about to be cut again); the opener only a fade-out,
    the closer only a fade-in plus, when ``fade_out_bars`` is set, an
    equal-power ramp to silence on its own tail. Subsumes Milestone A
    exactly — for a 2-track plan this reproduces the old direct
    ``render_junction`` delegation byte-for-byte.

    ``transition_renderer.render_junction`` is not called for tier-3
    junctions any more — tier 3 (``length_bars == 0``) has no blend content
    to render; the anti-click fade it used to contribute is applied here
    directly via the same shared ``linear_edge_fade`` helper. It remains the
    right call for a future tier with real blend content, out of scope here
    since none is implemented yet.
    """
    n = len(mix_plan.tracks)
    if len(mix_plan.junctions) != n - 1:
        raise ValueError(
            "render_mix requires len(junctions) == len(tracks) - 1; got "
            f"{n} tracks and {len(mix_plan.junctions)} junctions"
        )

    segments: list[np.ndarray] = []
    for i, track in enumerate(mix_plan.tracks):
        audio = load_audio(track.path)
        sample_rate = audio.sample_rate

        if i == 0:
            entry = track.cue_in if track.cue_in is not None else 0.0
        else:
            entry = mix_plan.junctions[i - 1].cue_in

        if i == n - 1:
            exit_ = track.cue_out if track.cue_out is not None else _natural_end(audio)
        else:
            exit_ = mix_plan.junctions[i].cue_out

        segment = audio.samples[_to_sample(entry, sample_rate) : _to_sample(exit_, sample_rate), :]

        if i > 0:  # entered via a cut
            segment = linear_edge_fade(segment, sample_rate, fade_in=True)
        if i < n - 1:  # exits via a cut
            segment = linear_edge_fade(segment, sample_rate, fade_in=False)
        if i == n - 1 and track.fade_out_bars is not None:  # §9 Q3
            duration = track.fade_out_bars * mix_plan.junctions[-1].bar_seconds
            segment = equal_power_fade_to_silence(segment, sample_rate, duration)

        segments.append(segment)

    return StereoPCM(samples=np.concatenate(segments, axis=0), sample_rate=SAMPLE_RATE)
