import pytest
from pydantic import ValidationError

from experiments.waveform_llm_transition.config import REPO_ROOT, load_config
from experiments.waveform_llm_transition.scoring import (
    GroundTruthEntry,
    load_ground_truth,
    score_pair,
)

# 2.18 s bars, first downbeat at 0.52 s: bar 65 starts at 140.04 s (2:20).
DOWNBEATS = [0.52 + 2.18 * i for i in range(95)]


def test_scored_pair():
    entry = GroundTruthEntry(exit_a="2:20", entry_b="0:01", rating=4, note="clean drop-in")
    score = score_pair(entry, DOWNBEATS, DOWNBEATS, exit_bar_a=69, entry_bar_b=1)
    assert score.marked
    assert score.exit_error_bars == 4
    assert score.exit_error_s == pytest.approx(0.52 + 2.18 * 68 - 140)
    assert score.entry_error_bars == 0
    assert (score.rating, score.note) == (4, "clean drop-in")


def test_llm_earlier_than_user_is_negative():
    score = score_pair(GroundTruthEntry(exit_a="2:20"), DOWNBEATS, DOWNBEATS, 61, 1)
    assert score.exit_error_bars == -4
    assert score.entry_error_bars is None


def test_no_ground_truth_yet(tmp_path):
    assert load_ground_truth(tmp_path / "missing.yaml") == {}
    assert score_pair(None, DOWNBEATS, DOWNBEATS, 65, 1).marked is False
    assert score_pair(GroundTruthEntry(), DOWNBEATS, DOWNBEATS, 65, 1).marked is False


def test_committed_template_has_blank_entries_for_both_pairs():
    # Extra entries (one-off pairs run via --config) may be filled in; the configured
    # pairs' entries stay blank until the user marks them.
    cfg = load_config()
    entries = load_ground_truth(REPO_ROOT / cfg.ground_truth)
    configured = {p.pair_id for p in cfg.pairs}
    assert configured <= set(entries)
    assert all(entries[pair_id] == GroundTruthEntry() for pair_id in configured)


def test_rating_out_of_range_rejected():
    with pytest.raises(ValidationError):
        GroundTruthEntry(rating=6)
