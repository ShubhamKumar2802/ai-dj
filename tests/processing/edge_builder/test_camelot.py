import pytest

from processing.edge_builder.camelot import key_distance, reachable_keys, wheel_distance


def test_wheel_distance_wraps_around():
    assert wheel_distance(12, 1) == 1
    assert wheel_distance(1, 12) == 1


def test_wheel_distance_no_wrap():
    assert wheel_distance(3, 5) == 2


def test_same_key_scores_zero():
    assert key_distance("8A", "8A") == pytest.approx(0.00)


def test_perfect_fifth_same_letter_scores_quarter():
    assert key_distance("8A", "9A") == pytest.approx(0.25)


def test_relative_major_minor_scores_quarter():
    assert key_distance("8A", "8B") == pytest.approx(0.25)


def test_diagonal_scores_full():
    assert key_distance("8A", "9B") == pytest.approx(1.00)


def test_wheel_wraparound_12_to_1_same_letter():
    assert key_distance("12A", "1A") == pytest.approx(0.25)


def test_otherwise_scales_with_wheel_distance():
    assert key_distance("1A", "4A") == pytest.approx(3 / 6)


def test_otherwise_reaches_max_at_wheel_distance_six():
    assert key_distance("1A", "7A") == pytest.approx(1.0)


@pytest.mark.parametrize("key_a,key_b", [(None, "8A"), ("8A", None), (None, None), ("bogus", "8A")])
def test_null_or_unparseable_key_scores_half_never_zero(key_a, key_b):
    assert key_distance(key_a, key_b) == pytest.approx(0.5)


def test_reachable_keys_has_exactly_the_four_free_moves():
    # same key; +-1 same letter (perfect fifth); same number, flip letter
    # (relative major/minor) — resources/ai-dj-domain-and-architecture.md §1.1
    assert reachable_keys("8A") == {"8A", "7A", "9A", "8B"}


def test_reachable_keys_wraps_at_12_to_1():
    assert reachable_keys("12A") == {"12A", "11A", "1A", "12B"}
    assert reachable_keys("1A") == {"1A", "12A", "2A", "1B"}


def test_reachable_keys_does_not_include_the_diagonal():
    # 9B (wheel_distance 1, letters differ) is the "avoid the diagonal" case —
    # explicitly not a free move (§1.1's table only has 3 non-trivial moves).
    assert "9B" not in reachable_keys("8A")


@pytest.mark.parametrize("key", [None, "bogus", "13A", "8C"])
def test_reachable_keys_empty_for_none_or_unparseable(key):
    assert reachable_keys(key) == set()
