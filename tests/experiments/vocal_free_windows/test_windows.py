import pytest

from experiments.vocal_free_windows.windows import (
    NoExitWindow,
    Window,
    find_windows,
    pick_exit,
)

SUNG = 0.1  # -20 dBFS
QUIET = 0.001  # -60 dBFS-ish, 40 dB under SUNG


def _times(n: int, bar_s: float = 2.0) -> list[tuple[float, float]]:
    return [(i * bar_s, (i + 1) * bar_s) for i in range(n)]


def _levels(n: int, quiet_bars: set[int]) -> list[float]:
    """1-based `quiet_bars` are vocal-free; the rest are sung."""
    return [QUIET if bar in quiet_bars else SUNG for bar in range(1, n + 1)]


def _find(levels, min_bars=2):
    return find_windows(levels, _times(len(levels)), 18, -60, min_bars)


def test_breath_between_lines_is_not_a_window():
    assert _find(_levels(20, {10})) == []


def test_instrumental_break():
    windows = _find(_levels(80, set(range(57, 61))))
    assert windows == [Window(57, 60, 112.0, 120.0)]


def test_instrumental_track_is_one_window():
    windows = _find([0.0] * 30)
    assert windows == [Window(1, 30, 0.0, 60.0)]


def test_relative_threshold():
    levels = _levels(80, set(range(57, 61)) | set(range(5, 9)))
    quieter = [v * 10 ** (-10 / 20) for v in levels]
    assert _find(levels) == _find(quieter)


def test_window_at_track_end_is_closed():
    assert _find(_levels(10, {9, 10})) == [Window(9, 10, 16.0, 20.0)]


def _w(first, last):
    return Window(first, last, (first - 1) * 2.0, last * 2.0)


def test_first_window_after_bar_32():
    windows = [_w(1, 8), _w(41, 42), _w(73, 80)]
    assert pick_exit(windows, 32, 2).first_bar == 41


def test_window_started_before_bar_33_is_skipped():
    assert pick_exit([_w(30, 36), _w(73, 80)], 32, 2).first_bar == 73


def test_window_too_short_for_overlap_is_skipped():
    assert pick_exit([_w(41, 42), _w(73, 80)], 32, 4).first_bar == 73


def test_no_usable_window():
    with pytest.raises(NoExitWindow, match="after bar 32"):
        pick_exit([_w(1, 8), _w(30, 36)], 32, 2)


@pytest.mark.parametrize("overlap_bars", [1, 2, 4])
def test_overlap_bars_lie_inside_exit_window(overlap_bars):
    exit_window = pick_exit([_w(41, 42), _w(50, 53), _w(73, 80)], 32, overlap_bars)
    overlap = range(exit_window.first_bar, exit_window.first_bar + overlap_bars)
    assert all(exit_window.first_bar <= bar <= exit_window.last_bar for bar in overlap)
