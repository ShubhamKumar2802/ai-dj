import pytest

from processing.edge_builder.config import EdgeBuilderConfig
from processing.edge_builder.tiers import eligible_pool, eligible_tiers, tier_penalty


def test_eligible_pool_drops_excluded(make_track):
    ok = make_track(id="ok", status="ok")
    excluded = make_track(id="excluded", status="excluded")
    pool = eligible_pool([ok, excluded])
    assert [t.id for t in pool] == ["ok"]


def test_eligible_pool_drops_bar_less_tracks(make_track):
    has_bars = make_track(id="has-bars", downbeat_times=[0.0, 2.0])
    bar_less = make_track(id="bar-less", downbeat_times=[0.0])
    pool = eligible_pool([has_bars, bar_less])
    assert [t.id for t in pool] == ["has-bars"]


def test_eligible_pool_drops_non_positive_bpm(make_track):
    # Guards junction_plan's bar_seconds division (spec v2 §5, §6).
    ok = make_track(id="ok", bpm=120.0)
    zero_bpm = make_track(id="zero", bpm=0.0)
    negative_bpm = make_track(id="negative", bpm=-1.0)
    pool = eligible_pool([ok, zero_bpm, negative_bpm])
    assert [t.id for t in pool] == ["ok"]


def test_wide_bpm_ratio_removes_tier_2_but_not_3_4_5(make_track):
    config = EdgeBuilderConfig()
    track_a = make_track(bpm=120.0)
    track_b = make_track(bpm=140.0)  # ratio ~0.167, well past the 0.03 default gate
    tiers = eligible_tiers(track_a, track_b, config)
    assert 2 not in tiers
    assert {3, 4, 5} <= tiers


def test_narrow_bpm_ratio_keeps_tier_2(make_track):
    config = EdgeBuilderConfig()
    track_a = make_track(bpm=120.0)
    track_b = make_track(bpm=121.0)  # ratio ~0.0083, inside the 0.03 default gate
    tiers = eligible_tiers(track_a, track_b, config)
    assert 2 in tiers


@pytest.mark.parametrize("cut_only_side", ["a", "b"])
def test_cut_only_on_either_side_removes_tier_2(cut_only_side, make_track):
    config = EdgeBuilderConfig()
    track_a = make_track(bpm=120.0, status="cut_only" if cut_only_side == "a" else "ok")
    track_b = make_track(bpm=120.0, status="cut_only" if cut_only_side == "b" else "ok")
    tiers = eligible_tiers(track_a, track_b, config)
    assert 2 not in tiers


def test_penalty_degenerates_to_single_table_when_templates_match():
    config = EdgeBuilderConfig()
    assert tier_penalty(3, "edm", "edm", config) == pytest.approx(config.tier_penalties_edm[3])
    assert tier_penalty(4, "film", "film", config) == pytest.approx(config.tier_penalties_film[4])


def test_penalty_averages_across_mismatched_templates():
    config = EdgeBuilderConfig()
    expected = (config.tier_penalties_edm[3] + config.tier_penalties_film[3]) / 2.0
    assert tier_penalty(3, "edm", "film", config) == pytest.approx(expected)


def test_unknown_template_shares_film_table():
    config = EdgeBuilderConfig()
    assert tier_penalty(3, "unknown", "unknown", config) == pytest.approx(
        config.tier_penalties_film[3]
    )
