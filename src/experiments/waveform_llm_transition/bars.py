"""Bar <-> time arithmetic. Bar N (counting from 1) starts at the Nth detected downbeat —
the one numbering used on the images, in the LLM's answers, for rendering and for scoring.
"""

import bisect
import re

from experiments.waveform_llm_transition.schema import Disagreement

_MMSS = re.compile(r"^\s*(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\s*$")


def range_error(which: str, downbeats: list[float], bar: int) -> str | None:
    """None if `bar` exists in the track, else a message like
    "exit bar 200 out of range (1–95)"."""
    if 1 <= bar <= len(downbeats):
        return None
    return f"{which} bar {bar} out of range (1–{len(downbeats)})"


def bar_start(downbeats: list[float], bar: int) -> float:
    if range_error("", downbeats, bar) is not None:
        raise IndexError(f"bar {bar} out of range (1–{len(downbeats)})")
    return downbeats[bar - 1]


def bar_duration(downbeats: list[float], bar: int) -> float:
    """Seconds from bar `bar`'s downbeat to the next; the last bar reuses the previous gap."""
    index = bar - 1
    if index + 1 < len(downbeats):
        return downbeats[index + 1] - downbeats[index]
    return downbeats[index] - downbeats[index - 1]


def nearest_bar(downbeats: list[float], seconds: float) -> int:
    """The bar whose downbeat is closest to `seconds` (ties go to the earlier bar)."""
    i = bisect.bisect_left(downbeats, seconds)
    if i == 0:
        return 1
    if i == len(downbeats):
        return len(downbeats)
    return i if seconds - downbeats[i - 1] <= downbeats[i] - seconds else i + 1


def parse_mmss(text: str) -> float:
    """"2:21" -> 141.0, "1:02:03" -> 3723.0, "0:01.5" -> 1.5. Raises ValueError otherwise."""
    match = _MMSS.match(text)
    if not match:
        raise ValueError(f"not an mm:ss time: {text!r}")
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)


def format_mmss(seconds: float) -> str:
    """141.0 -> "2:21" (whole seconds, truncated, matching the tile axis labels)."""
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def check_disagreement(
    which: str, downbeats: list[float], bar: int, stated_time: str
) -> Disagreement | None:
    """A Disagreement when the LLM's mm:ss for `bar` is more than one bar's duration away
    from the bar's real start (or isn't a time at all); None when they agree."""
    real = bar_start(downbeats, bar)
    try:
        stated = parse_mmss(stated_time)
    except ValueError:
        return Disagreement(which, bar, stated_time, real, None)
    delta = stated - real
    if abs(delta) > bar_duration(downbeats, bar):
        return Disagreement(which, bar, stated_time, real, delta)
    return None
