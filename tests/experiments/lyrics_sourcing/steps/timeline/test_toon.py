import numpy as np
import pytest

from experiments.lyrics_sourcing.schema import (
    LyricSegment,
    Timeline,
    TimelineHeader,
    TimelineRow,
)
from experiments.lyrics_sourcing.steps.timeline.toon import encode_timeline, encode_value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (True, "true"),
        (3, "3"),
        (-12.3, "-12.3"),
        (np.float64(1.2), "1.2"),  # analysis modules hand back NumPy scalars
        (np.int64(7), "7"),
        ("plain words", "plain words"),
        ("", '""'),
        ("a,b", '"a,b"'),
        ("key: value", '"key: value"'),
        ('say "hi"', '"say \\"hi\\""'),
        ("back\\slash", '"back\\\\slash"'),
        ("two\nlines", '"two\\nlines"'),
        (" padded", '" padded"'),
        ("42", '"42"'),
        ("true", '"true"'),
        ("null", '"null"'),
        ("hook_in;hook_exit", "hook_in;hook_exit"),
    ],
)
def test_encode_value_quoting(value, expected):
    assert encode_value(value) == expected


def _row(t: int, **overrides) -> TimelineRow:
    values = dict(
        t=t, bar=None, downbeat=0, beats=0, energy_lufs=None, vocal=None, rms=None, low=None,
        high=None, centroid=None, flux=None, chroma=None, phrase=None, cue=None, riser=0,
        lyric=None,
    )  # fmt: skip
    values.update(overrides)
    return TimelineRow(**values)


def test_golden_timeline():
    header = TimelineHeader(
        title="Abhi Toh Party",
        artist=None,
        video_id="abc",
        duration=1.5,
        bpm=120.0,
        bpm_confidence=0.9,
        key="8A",
        key_confidence=None,
        lufs_integrated=-9.0,
        true_peak=-1.0,
        structure_template="film",
        grid_start=1.0,
        phrase_length_bars=None,
        cue_status="ok",
        lyrics_source="ytmusic",
        lyrics_verdict="matched",
        lyrics_offset_s=0.0,
    )
    rows = [
        _row(0),
        _row(1, bar=0, downbeat=1, beats=2, energy_lufs=-8.5, vocal=0.3, rms=1.0, low=0.0,
             high=0.5, centroid=0.25, flux=0.75, chroma="C#", phrase=0.82, cue="first_downbeat",
             lyric="Abhi toh, party"),
    ]  # fmt: skip
    lyrics = [LyricSegment(1.2, 1.5, "Abhi toh, party", 0.9)]
    expected = (
        "title: Abhi Toh Party\n"
        "artist:\n"
        "video_id: abc\n"
        "duration: 1.5\n"
        "bpm: 120.0\n"
        "bpm_confidence: 0.9\n"
        "key: 8A\n"
        "key_confidence:\n"
        "lufs_integrated: -9.0\n"
        "true_peak: -1.0\n"
        "structure_template: film\n"
        "grid_start: 1.0\n"
        "phrase_length_bars:\n"
        "cue_status: ok\n"
        "lyrics_source: ytmusic\n"
        "lyrics_verdict: matched\n"
        "lyrics_offset_s: 0.0\n"
        "\n"
        "timeline[2]{t,bar,downbeat,beats,energy_lufs,vocal,rms,low,high,centroid,flux,chroma,"
        "phrase,cue,riser,lyric}:\n"
        "  0,,0,0,,,,,,,,,,,0,\n"
        '  1,0,1,2,-8.5,0.3,1.0,0.0,0.5,0.25,0.75,C#,0.82,first_downbeat,0,"Abhi toh, party"\n'
        "\n"
        "lyrics[1]{start,end,text}:\n"
        '  1.2,1.5,"Abhi toh, party"\n'
    )
    assert encode_timeline(Timeline(header=header, rows=rows, lyrics=lyrics)) == expected
