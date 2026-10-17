"""LRC parsing (spec §4.2). Pure."""

import re

from experiments.lyrics_sourcing.schema import LyricLine

_TIMESTAMP = re.compile(r"\[(\d+):(\d{1,2}(?:[.:]\d{1,3})?)\]")
_METADATA_TAG = re.compile(r"^\[([A-Za-z]+):(.*)\]$")


def parse_lrc(text: str) -> list[LyricLine]:
    """One LyricLine per (timestamp, text) pair, sorted, with `end` = next line's start.

    - `[00:12.00][01:30.00] text` yields two lines.
    - `[offset:+ms]`: positive makes lyrics appear *earlier* (LRC semantics), so it is
      subtracted from every timestamp.
    - Other metadata tags (`[ar:]`, `[ti:]`, `[length:]`, ...) and empty lines are dropped.
    """
    offset_s = 0.0
    entries: list[tuple[float, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        tag = _METADATA_TAG.match(line)
        if tag and not _TIMESTAMP.match(line):
            if tag.group(1).lower() == "offset":
                try:
                    offset_s = int(tag.group(2).strip()) / 1000
                except ValueError:
                    pass
            continue

        stamps: list[float] = []
        pos = 0
        while match := _TIMESTAMP.match(line, pos):
            stamps.append(int(match.group(1)) * 60 + float(match.group(2).replace(":", ".")))
            pos = match.end()

        lyric = line[pos:].strip()
        if not stamps or not lyric:
            continue
        entries.extend((stamp, lyric) for stamp in stamps)

    entries.sort(key=lambda entry: entry[0])
    starts = [round(max(0.0, stamp - offset_s), 3) for stamp, _ in entries]
    return [
        LyricLine(
            start=start,
            end=starts[i + 1] if i + 1 < len(starts) else None,
            text=lyric,
        )
        for i, (start, (_, lyric)) in enumerate(zip(starts, entries))
    ]
