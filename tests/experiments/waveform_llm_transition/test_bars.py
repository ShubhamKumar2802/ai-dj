import pytest

from experiments.waveform_llm_transition.bars import (
    bar_start,
    check_disagreement,
    format_mmss,
    nearest_bar,
    parse_mmss,
    range_error,
)

# 2.18 s bars (110 BPM), first downbeat at 0.52 s.
DOWNBEATS = [0.52 + 2.18 * i for i in range(95)]


def test_bar_to_time():
    downbeats = [0.52, 2.70, 4.88]
    assert bar_start(downbeats, 1) == 0.52
    assert bar_start(downbeats, 3) == 4.88


def test_bar_beyond_track_end():
    assert range_error("exit", DOWNBEATS, 200) == "exit bar 200 out of range (1–95)"
    assert range_error("entry", DOWNBEATS, 0) == "entry bar 0 out of range (1–95)"
    assert range_error("exit", DOWNBEATS, 95) is None
    with pytest.raises(IndexError):
        bar_start(DOWNBEATS, 96)


def test_mmss_round_trip():
    assert parse_mmss("2:21") == 141.0
    assert parse_mmss("0:01.5") == 1.5
    assert parse_mmss("1:02:03") == 3723.0
    assert format_mmss(141.9) == "2:21"
    with pytest.raises(ValueError):
        parse_mmss("bar 65")


def test_nearest_bar():
    assert nearest_bar(DOWNBEATS, 0.0) == 1
    assert nearest_bar(DOWNBEATS, 0.52 + 2.18 * 64 + 0.5) == 65
    assert nearest_bar(DOWNBEATS, 0.52 + 2.18 * 64 + 1.7) == 66
    assert nearest_bar(DOWNBEATS, 10_000) == 95


def test_bar_and_time_disagree():
    # Bar 65 starts at 140.04 s (2:20); the LLM says 1:40.
    found = check_disagreement("exit_a", DOWNBEATS, 65, "1:40")
    assert found is not None
    assert found.delta_s == pytest.approx(100 - (0.52 + 2.18 * 64))


def test_bar_and_time_agree_within_one_bar():
    assert check_disagreement("exit_a", DOWNBEATS, 65, "2:21") is None


def test_unparseable_time_is_a_disagreement():
    found = check_disagreement("entry_b", DOWNBEATS, 1, "start")
    assert found is not None and found.delta_s is None
