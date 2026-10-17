import pytest

from experiments.lyrics_sourcing.schema import Transcript
from experiments.lyrics_sourcing.steps.time_match.align import align
from tests.experiments.lyrics_sourcing.builders import lyric_lines, transcript_from

DURATION = 120.0


def test_identical_timing_is_matched(cfg):
    lines = lyric_lines()
    alignment, inliers = align("ytmusic", lines, transcript_from(lines), DURATION, cfg.time_match)
    assert alignment.verdict == "matched"
    assert alignment.offset_s == pytest.approx(0.0, abs=0.01)
    assert alignment.line_coverage == 1.0
    assert len(inliers) == len(lines)


def test_constant_shift_is_offset_corrected(cfg):
    lines = lyric_lines()
    transcript = transcript_from(lines, shift=7.3)
    alignment, _ = align("lrclib", lines, transcript, DURATION, cfg.time_match)
    assert alignment.verdict == "offset_corrected"
    assert alignment.offset_s == pytest.approx(7.3, abs=0.05)
    assert alignment.drift_slope == pytest.approx(1.0, abs=0.01)


def test_repeated_chorus_does_not_mislead_the_vote(cfg):
    # The chorus line appears 3x, so each chorus lyric line also matches the *other* two
    # occurrences (wrong deltas of +-48s). The vote must still land on the true offset.
    lines = lyric_lines()
    transcript = transcript_from(lines, shift=3.0)
    alignment, inliers = align("ytmusic", lines, transcript, DURATION, cfg.time_match)
    assert alignment.offset_s == pytest.approx(3.0, abs=0.05)
    assert all(abs(a.delta - 3.0) < 0.1 for a in inliers.values())


def test_sparse_transcript_is_unverifiable(cfg):
    lines = lyric_lines()
    sparse = transcript_from(lines[:1])  # ~5 words in 2 minutes
    alignment, _ = align("ytmusic", lines, sparse, DURATION, cfg.time_match)
    assert alignment.verdict == "unverifiable"


def test_wrong_song_is_rejected(cfg):
    lines = lyric_lines()
    other = lyric_lines(
        texts=[f"completely different words number {n} here today" for n in range(10)]
    )
    alignment, _ = align("lrclib", lines, transcript_from(other), DURATION, cfg.time_match)
    assert alignment.verdict == "rejected"


def test_empty_transcript_is_unverifiable(cfg):
    empty = Transcript(language=None, segments=[], whisper_config_id="x", model="x")
    alignment, _ = align("ytmusic", lyric_lines(), empty, DURATION, cfg.time_match)
    assert alignment.verdict == "unverifiable"
    assert alignment.offset_s is None
