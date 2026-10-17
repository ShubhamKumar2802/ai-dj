from experiments.lyrics_sourcing.schema import Alignment, LyricLine, LyricsCandidate
from experiments.lyrics_sourcing.steps.time_match.align import Anchor
from experiments.lyrics_sourcing.steps.time_match.resolve import lyric_segments, resolve
from tests.experiments.lyrics_sourcing.builders import lyric_lines, transcript_from

DURATION = 120.0


def _candidate(source: str, lines=None) -> LyricsCandidate:
    return LyricsCandidate(
        source=source,
        source_ref=None,
        status="synced",
        lines=lines or lyric_lines(),
        plain_text=None,
        reference_duration=None,
        error=None,
        fetched_at="t",
    )


def _alignment(source, verdict, coverage=0.8, offset=0.0) -> Alignment:
    return Alignment(
        source=source,
        verdict=verdict,
        offset_s=offset,
        anchorable_lines=10,
        inlier_lines=8,
        line_coverage=coverage,
        median_abs_residual_s=0.1,
        drift_slope=1.0,
        transcript_density_wpm=100.0,
        urdu_script_words=0,
    )


def test_coverage_tie_goes_to_priority_order(cfg):
    transcript = transcript_from(lyric_lines())
    aligned = [
        (_candidate("ytmusic"), _alignment("ytmusic", "matched", coverage=0.78), {}),
        (_candidate("lrclib"), _alignment("lrclib", "matched", coverage=0.80), {}),
    ]
    assert resolve(aligned, transcript, DURATION, cfg.time_match).source == "ytmusic"


def test_clearly_higher_coverage_wins(cfg):
    transcript = transcript_from(lyric_lines())
    aligned = [
        (_candidate("ytmusic"), _alignment("ytmusic", "matched", coverage=0.5), {}),
        (_candidate("lrclib"), _alignment("lrclib", "matched", coverage=0.9), {}),
    ]
    assert resolve(aligned, transcript, DURATION, cfg.time_match).source == "lrclib"


def test_offset_corrected_shifts_lines_and_sets_confidence(cfg):
    lines = lyric_lines()
    aligned = [
        (
            _candidate("lrclib", lines),
            _alignment("lrclib", "offset_corrected", offset=5.0),
            {0: Anchor(line_index=0, delta=5.0, score=90.0)},
        )
    ]
    synced = resolve(aligned, transcript_from(lines), DURATION, cfg.time_match)
    assert synced.verdict == "offset_corrected"
    assert synced.offset_applied_s == 5.0
    assert synced.segments[0].start == lines[0].start + 5.0
    assert synced.segments[0].confidence == 0.9
    assert synced.segments[1].confidence is None


def test_unverifiable_beats_whisper(cfg):
    aligned = [(_candidate("ytmusic"), _alignment("ytmusic", "unverifiable"), {})]
    synced = resolve(aligned, transcript_from(lyric_lines()), DURATION, cfg.time_match)
    assert (synced.source, synced.verdict, synced.offset_applied_s) == (
        "ytmusic",
        "unverifiable",
        0.0,
    )


def test_all_rejected_falls_back_to_whisper(cfg):
    aligned = [(_candidate("lrclib"), _alignment("lrclib", "rejected"), {})]
    transcript = transcript_from(lyric_lines())
    synced = resolve(aligned, transcript, DURATION, cfg.time_match)
    assert (synced.source, synced.verdict) == ("whisper", "fallback")
    assert len(synced.segments) == len(transcript.segments)
    assert synced.segments[0].confidence == 0.9
    assert len(synced.alignments) == 1


def test_no_candidates_falls_back_to_whisper(cfg):
    synced = resolve([], transcript_from(lyric_lines()), DURATION, cfg.time_match)
    assert synced.source == "whisper"


def test_line_ends_shift_clamp_and_drop():
    lines = [
        LyricLine(start=1.0, end=2.0, text="a"),  # shifted to -2..-1: wholly before 0, dropped
        LyricLine(start=4.0, end=None, text="b"),  # next start 30 -> capped at max_line_s
        LyricLine(start=30.0, end=31.0, text="c"),  # own end used
        LyricLine(start=40.0, end=None, text="d"),  # last line: min(start + max, duration)
    ]
    segments, dropped = lyric_segments(lines, -3.0, 40.0, 10.0, {})
    assert dropped == 1
    assert [(s.start, s.end, s.text) for s in segments] == [
        (1.0, 11.0, "b"),
        (27.0, 28.0, "c"),
        (37.0, 40.0, "d"),
    ]
