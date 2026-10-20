"""Vocal-free windows from per-bar vocal levels, and the exit pick in track A.

Pure functions over per-bar series and bar times — no audio. Bars are numbered from 1
(bar N = the bar starting at the Nth downbeat = `per_bar_features[N - 1]`).
"""

from dataclasses import asdict, dataclass

import numpy as np

_EPS = 1e-10
REFERENCE_PERCENTILE = 95  # the same percentile edge_builder normalises vocal_mask by


@dataclass(frozen=True)
class Window:
    first_bar: int  # 1-based, inclusive
    last_bar: int  # 1-based, inclusive
    start_s: float  # start of first_bar
    end_s: float  # end of last_bar

    @property
    def length(self) -> int:
        return self.last_bar - self.first_bar + 1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Threshold:
    reference_db: float
    cutoff_db: float


class NoExitWindow(Exception):
    """No vocal-free window in A qualifies as the exit."""


def to_db(levels: list[float]) -> np.ndarray:
    return 20.0 * np.log10(np.asarray(levels, dtype=float) + _EPS)


def threshold(levels: list[float], threshold_db: float, floor_dbfs: float) -> Threshold:
    """The cutoff below which a bar is vocal-free: `threshold_db` under the track's own p95
    bar level, or `floor_dbfs`, whichever is higher (design.md). The floor wins on a
    silent stem, so every bar of an instrumental counts as vocal-free."""
    level_db = to_db(levels)
    reference = float(np.percentile(level_db, REFERENCE_PERCENTILE)) if len(level_db) else -200.0
    return Threshold(reference_db=reference, cutoff_db=max(reference - threshold_db, floor_dbfs))


def vocal_free_mask(levels: list[float], cutoff_db: float) -> list[bool]:
    return [bool(v) for v in to_db(levels) < cutoff_db]


def find_windows(
    levels: list[float],
    bar_times: list[tuple[float, float]],
    threshold_db: float,
    floor_dbfs: float,
    min_bars: int,
) -> list[Window]:
    """Runs of at least `min_bars` consecutive vocal-free bars. `bar_times[i]` is bar i+1's
    `(start_time, end_time)`."""
    cutoff = threshold(levels, threshold_db, floor_dbfs).cutoff_db
    mask = vocal_free_mask(levels, cutoff)

    windows = []
    run_start = None
    for i, free in enumerate([*mask, False]):  # sentinel closes a run at the end
        if free and run_start is None:
            run_start = i
        elif not free and run_start is not None:
            if i - run_start >= min_bars:
                windows.append(
                    Window(
                        first_bar=run_start + 1,
                        last_bar=i,
                        start_s=bar_times[run_start][0],
                        end_s=bar_times[i - 1][1],
                    )
                )
            run_start = None
    return windows


def pick_exit(windows: list[Window], exit_after_bar: int, overlap_bars: int) -> Window:
    """The earliest window that *starts* after `exit_after_bar` and is at least
    `overlap_bars` long, so the overlap stays inside it. The exit is its first bar."""
    for window in windows:
        if window.first_bar > exit_after_bar and window.length >= overlap_bars:
            return window
    raise NoExitWindow(
        f"track A has no vocal-free window starting after bar {exit_after_bar} "
        f"that is at least {overlap_bars} bars long"
    )
