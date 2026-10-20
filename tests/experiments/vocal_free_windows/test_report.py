import pytest
import yaml
from pydantic import ValidationError

from experiments.vocal_free_windows.report import (
    OutputInfo,
    PairRatings,
    RunResult,
    TrackInfo,
    load_ratings,
    render_summary,
)
from experiments.vocal_free_windows.windows import Window

PAIR = "Y7G-tYRzwYY__KxCjVIFxZNo"


def _result(**overrides) -> RunResult:
    base = dict(
        pair_id=PAIR,
        a=TrackInfo("Subha Hone Na De", "a.mp3", 132.0, -8.1),
        b=TrackInfo("Lat Lag Gayee", "b.mp3", 130.7, -12.5),
        windows=[Window(1, 3, 0.5, 6.0), Window(57, 63, 102.26, 114.99)],
        cutoff_db=-31.1,
        exit_after_bar=32,
        exit_window=Window(57, 63, 102.26, 114.99),
        entry_s=0.31,
        gain_db=4.4,
        overlap_bars=2,
        bass_swap_bars=16,
        drift_overlap_ms=35.8,
        drift_bass_swap_ms=286.5,
        image_path="out/A_vocal_lane.png",
        outputs=[
            OutputInfo("cut", "out/transition_cut.wav", -0.4),
            OutputInfo("overlap", "out/transition_overlap.wav", 0.6),
            OutputInfo("bass_swap", "out/transition_bass_swap.wav", 1.2),
        ],
    )
    return RunResult(**{**base, **overrides})


def test_success_summary():
    text = render_summary(_result(), PairRatings())
    for expected in [
        "bars 57–63", "bars 1–3", "Exit A:** bar 57", "1:42", "Entry B:** bar 1",
        "+4.4 dB", "36 ms", "286 ms", "out/A_vocal_lane.png", "out/transition_cut.wav",
        "out/transition_overlap.wav", "out/transition_bass_swap.wav", "peak +1.2 dBFS",
    ]:
        assert expected in text, expected


def test_skipped_bass_swap_shows_reason():
    outputs = [
        OutputInfo("cut", "c.wav", -1.0),
        OutputInfo("overlap", "o.wav", -1.0),
        OutputInfo("bass_swap", skipped="track A has only 10 bars after the exit"),
    ]
    text = render_summary(_result(outputs=outputs), PairRatings())
    assert "bass_swap:** skipped — track A has only 10 bars" in text


def test_failed_run_shows_reason_and_no_outputs():
    text = render_summary(
        _result(failure="track A has no vocal-free window starting after bar 32",
                exit_window=None, outputs=[]),
        PairRatings(),
    )
    assert "Failed:** track A has no vocal-free window" in text
    assert ".wav" not in text


def test_not_rated_yet(tmp_path):
    ratings = load_ratings(tmp_path / "missing.yaml", PAIR)
    text = render_summary(_result(), ratings)
    assert text.count("not rated") == 3


def test_ratings_are_shown(tmp_path):
    path = tmp_path / "gt.yaml"
    path.write_text(yaml.safe_dump(
        {"pairs": {PAIR: {"cut": {"rating": 4, "note": "clean"}}}}
    ))
    text = render_summary(_result(), load_ratings(path, PAIR))
    assert "cut:** 4/5 — clean" in text
    assert text.count("not rated") == 2


def test_bad_rating_rejected(tmp_path):
    path = tmp_path / "gt.yaml"
    path.write_text(yaml.safe_dump({"pairs": {PAIR: {"cut": {"rating": 7}}}}))
    with pytest.raises(ValidationError):
        load_ratings(path, PAIR)


def test_committed_template_loads():
    from experiments.vocal_free_windows.config import load_config

    ratings = load_ratings(load_config().ground_truth, PAIR)
    assert isinstance(ratings, PairRatings)
