import numpy as np
import pytest

from render.playlist_renderer.render import equal_power_fade_to_silence, render_mix
from render.transition_renderer import render_junction

SAMPLE_RATE = 48000


def test_two_track_plan_matches_milestone_a_render_junction_exactly(
    make_pcm, make_mix_plan, fake_load_audio
):
    # Milestone B's general N-track path must subsume Milestone A: for a
    # 2-track/1-junction plan it no longer calls render_junction at all, but
    # the output must still be byte-for-byte what render_junction produces.
    plan = make_mix_plan(("a", "b"))
    audio_a = make_pcm(2.0, value=0.5)
    audio_b = make_pcm(3.0, value=-0.5)
    load = fake_load_audio({"a.mp3": audio_a, "b.mp3": audio_b})

    out = render_mix(plan, load)
    expected = render_junction(plan.junctions[0], audio_a, audio_b)

    assert np.array_equal(out.samples, expected.samples)
    assert out.sample_rate == expected.sample_rate == 48000


def test_interior_track_gets_both_a_fade_in_and_a_fade_out(
    make_pcm, make_mix_plan, fake_load_audio
):
    # The case Milestone A never exercised: a middle track was just cut into
    # (fade-in at its head) and is about to be cut again (fade-out at its tail).
    plan = make_mix_plan(("a", "b", "c"))
    audio = {t: make_pcm(3.0, value=0.6) for t in ("a", "b", "c")}
    load = fake_load_audio({f"{t}.mp3": p for t, p in audio.items()})

    out = render_mix(plan, load)

    # junctions: a->b cue_out=1.0/cue_in=0.2, b->c cue_out=1.0/cue_in=0.2 (conftest defaults)
    a_len = round(1.0 * SAMPLE_RATE)  # a's body: [0, 1.0)
    b_len = round((1.0 - 0.2) * SAMPLE_RATE)  # b's body: [0.2, 1.0)
    b_start = a_len
    b_end = a_len + b_len

    nf = round(5 / 1000 * SAMPLE_RATE)  # transition_renderer.fades.FADE_MS

    # b's head (just entered) ramps up from ~silence...
    assert abs(out.samples[b_start, 0]) < 0.05
    assert out.samples[b_start + nf, 0] == pytest.approx(0.6, abs=1e-2)
    # ...and b's tail (about to be cut again) ramps down to ~silence.
    assert abs(out.samples[b_end - 1, 0]) < 0.05
    assert out.samples[b_end - nf, 0] == pytest.approx(0.6, abs=1e-2)


def test_closer_with_fade_out_bars_ramps_the_final_tail_to_silence(
    make_pcm, make_mix_plan, fake_load_audio, make_track_ref
):
    plan = make_mix_plan(("a", "b"))
    plan.tracks[-1] = make_track_ref(id="b", fade_out_bars=4)
    audio_a = make_pcm(2.0, value=0.5)
    # Long enough that the 4-bar (8s, given bar_seconds=2.0) closer fade
    # doesn't overlap the 5ms head fade-in — keeps the two effects isolated.
    audio_b = make_pcm(20.0, value=-0.5)
    load = fake_load_audio({"a.mp3": audio_a, "b.mp3": audio_b})

    out = render_mix(plan, load)

    duration = 4 * plan.junctions[-1].bar_seconds  # 4 * 2.0s = 8.0s
    n_fade = round(duration * SAMPLE_RATE)

    assert out.samples[-1, 0] == pytest.approx(0.0, abs=1e-3)  # true silence at the very end
    # full level where the ramp starts
    assert out.samples[-n_fade, 0] == pytest.approx(-0.5, abs=1e-2)


def test_equal_power_fade_to_silence_does_not_mutate_input():
    segment = np.full((SAMPLE_RATE, 2), 0.7, dtype=np.float32)
    original = segment.copy()

    equal_power_fade_to_silence(segment, SAMPLE_RATE, duration_seconds=0.5)

    assert np.array_equal(segment, original)


def test_structural_guard_rejects_a_junction_count_mismatch(
    make_pcm, make_mix_plan, fake_load_audio
):
    plan = make_mix_plan(("a", "b", "c"))
    plan.junctions = plan.junctions[:1]  # malformed: 3 tracks but only 1 junction
    load = fake_load_audio({f"{t}.mp3": make_pcm(1.0) for t in ("a", "b", "c")})

    with pytest.raises(ValueError):
        render_mix(plan, load)
