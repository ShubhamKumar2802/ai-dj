import pytest

from processing.edge_builder.config import EdgeBuilderConfig
from processing.edge_builder.junction_plan import build_junction


def test_rate_a_is_always_one(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a", bpm=120.0)
    track_b = make_track(id="b", bpm=125.0)
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    for tier in (2, 3, 4, 5):
        junction = build_junction(track_a, track_b, cue_out, cue_in, tier, config)
        assert junction.rate_a == pytest.approx(1.0)


def test_rate_b_only_set_for_tier_2(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a", bpm=120.0)
    track_b = make_track(id="b", bpm=125.0)
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    tier2 = build_junction(track_a, track_b, cue_out, cue_in, 2, config)
    assert tier2.rate_b == pytest.approx(120.0 / 125.0)

    for tier in (3, 4, 5):
        junction = build_junction(track_a, track_b, cue_out, cue_in, tier, config)
        assert junction.rate_b == pytest.approx(1.0)


def test_ramp_bars_always_zero(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a")
    track_b = make_track(id="b")
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    for tier in (2, 3, 4, 5):
        junction = build_junction(track_a, track_b, cue_out, cue_in, tier, config)
        assert junction.ramp_bars == 0


def test_length_bars_per_tier(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a")
    track_b = make_track(id="b")
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    assert build_junction(track_a, track_b, cue_out, cue_in, 2, config).length_bars == 16
    assert build_junction(track_a, track_b, cue_out, cue_in, 3, config).length_bars == 0
    assert build_junction(track_a, track_b, cue_out, cue_in, 4, config).length_bars == 4
    assert build_junction(track_a, track_b, cue_out, cue_in, 5, config).length_bars == 8


def test_tier_2_envelope_breakpoints_match_spec(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a", bpm=120.0)
    track_b = make_track(id="b", bpm=120.0)
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    junction = build_junction(track_a, track_b, cue_out, cue_in, 2, config)

    envelopes = {(e.target, e.side): e.breakpoints for e in junction.envelopes}
    assert envelopes[("low", "b")] == [(0, 0.0), (8, 0.0), (12, 1.0)]
    assert envelopes[("low", "a")] == [(0, 1.0), (8, 1.0), (12, 0.0)]
    assert envelopes[("crossfader", "a")] == [(0, 0.0), (12, 1.0)]


def test_tier_3_and_4_have_no_envelopes(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a")
    track_b = make_track(id="b")
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    assert build_junction(track_a, track_b, cue_out, cue_in, 3, config).envelopes == []
    assert build_junction(track_a, track_b, cue_out, cue_in, 4, config).envelopes == []


def test_tier_5_has_single_high_ramp(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a")
    track_b = make_track(id="b")
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    junction = build_junction(track_a, track_b, cue_out, cue_in, 5, config)
    assert len(junction.envelopes) == 1
    envelope = junction.envelopes[0]
    assert envelope.target == "high"
    assert envelope.side == "a"
    assert envelope.breakpoints == [(0, 0.0), (8, 1.0)]


def test_bar_seconds_from_known_tempo(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a", bpm=120.0, beats_per_bar=4)
    track_b = make_track(id="b", bpm=120.0, beats_per_bar=4)
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    junction = build_junction(track_a, track_b, cue_out, cue_in, 2, config)
    # 120 BPM 4/4 -> one beat is 0.5s, one bar is 2.0s.
    assert junction.bar_seconds == pytest.approx(2.0)


def test_bar_seconds_uses_track_a_never_track_b(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a", bpm=120.0, beats_per_bar=4)
    track_b = make_track(id="b", bpm=90.0, beats_per_bar=4)
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    for tier in (2, 3, 4, 5):
        junction = build_junction(track_a, track_b, cue_out, cue_in, tier, config)
        assert junction.bar_seconds == pytest.approx(2.0)  # A's, not B's 2.666...


def test_bar_seconds_emitted_on_every_tier_including_tier_3(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a", bpm=128.0, beats_per_bar=4)
    track_b = make_track(id="b", bpm=128.0, beats_per_bar=4)
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    expected = 60.0 / 128.0 * 4
    for tier in (2, 3, 4, 5):
        junction = build_junction(track_a, track_b, cue_out, cue_in, tier, config)
        assert junction.bar_seconds == pytest.approx(expected)


def test_bar_seconds_respects_beats_per_bar(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a", bpm=120.0, beats_per_bar=3)
    track_b = make_track(id="b", bpm=120.0, beats_per_bar=4)
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    junction = build_junction(track_a, track_b, cue_out, cue_in, 3, config)
    assert junction.bar_seconds == pytest.approx(1.5)


def test_gain_db_left_at_zero(make_track, make_cue):
    config = EdgeBuilderConfig()
    track_a = make_track(id="a")
    track_b = make_track(id="b")
    cue_out = make_cue(position=100.0, kind="hook_exit")
    cue_in = make_cue(position=8.0, kind="intro_end")

    for tier in (2, 3, 4, 5):
        junction = build_junction(track_a, track_b, cue_out, cue_in, tier, config)
        assert junction.gain_db_a == pytest.approx(0.0)
        assert junction.gain_db_b == pytest.approx(0.0)
