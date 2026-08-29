import pytest

from processing.path_search.familiarity import (
    familiarity_array,
    familiarity_deficit,
    familiarity_of,
    pool_familiarity_mean,
)


def test_all_none_is_v1s_real_case_and_inert(make_track):
    pool = [make_track(id=str(i), familiarity_score=None) for i in range(5)]
    assert pool_familiarity_mean(pool) is None
    arr = familiarity_array(pool)
    assert list(arr) == [0.5] * 5
    # Every candidate path draws the same 0.5 -> the term cannot change any ranking.
    assert familiarity_deficit(arr[:2]) == pytest.approx(0.5)
    assert familiarity_deficit(arr[:4]) == pytest.approx(0.5)


def test_pool_mean_fallback_for_a_partially_scored_pool(make_track):
    pool = [
        make_track(id="a", familiarity_score=0.8),
        make_track(id="b", familiarity_score=0.4),
        make_track(id="c", familiarity_score=None),
    ]
    assert pool_familiarity_mean(pool) == pytest.approx(0.6)
    assert familiarity_of(pool[2], pool_familiarity_mean(pool)) == pytest.approx(0.6)
    assert familiarity_of(pool[0], pool_familiarity_mean(pool)) == pytest.approx(0.8)


def test_unknown_track_with_no_known_scores_is_neutral_not_zero(make_track):
    assert familiarity_of(make_track(familiarity_score=None), None) == 0.5


def test_deficit_direction_more_familiar_scores_lower():
    familiar = familiarity_deficit([0.9, 0.8, 0.85])
    unfamiliar = familiarity_deficit([0.2, 0.1, 0.15])
    assert familiar < unfamiliar
