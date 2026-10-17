from experiments.lyrics_sourcing.schema import LyricSegment, SyncedLyrics, TrackMetadata
from experiments.lyrics_sourcing.steps.timeline.per_second import build_per_second
from ingestion.cue_derivation.schema import Cue, CueDerivationResult, PhraseBoundary
from ingestion.feature_extractor.schema import PerBarFeatures, RawFeatures, RiserCandidate


def _bar(i: int, start: float, end: float, rms: float, chroma_peak: int) -> PerBarFeatures:
    chroma = [0.0] * 12
    chroma[chroma_peak] = 1.0
    return PerBarFeatures(i, start, end, rms, 1000.0 * (i + 1), 0.1 * i, 0.2, 0.3, chroma)


def _meta(duration: float = 9.4) -> TrackMetadata:
    raw = RawFeatures(
        content_hash="h",
        feature_extractor_version="2",
        source_path="a.mp3",
        duration=duration,
        sample_rate=48000,
        bpm=120.0,
        bpm_confidence=0.9,
        beat_times=[1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
        downbeat_times=[1.0, 3.0, 5.0],
        downbeat_confidence=0.8,
        beats_per_bar=4,
        # Bars cover 1.0-5.0 only: seconds 0 and 5+ are outside the grid.
        per_bar_features=[_bar(0, 1.0, 3.0, 0.2, 3), _bar(1, 3.0, 5.0, 0.6, 0)],
        lufs_integrated=-9.04,
        true_peak=-1.0,
        energy_curve=[-12.34, -8.0],
        vocal_band_energy=[0.5, 0.5],  # constant -> scaled to 0.0
        key="8A",
        key_confidence=0.7,
        riser_candidates=[RiserCandidate(2.0, 4.0, 0.7)],
    )
    cues = CueDerivationResult(
        grid_start=1.0,
        grid_confidence=0.9,
        free_intro_end=1.0,
        phrase_length_bars=None,
        phrase_grid=[PhraseBoundary(3.0, 1.234, 1.0)],
        structure_template="film",
        cue_ins=[Cue(1.0, "first_downbeat", 0.9), Cue(3.2, "hook_in", 0.6)],
        cue_outs=[Cue(3.9, "hook_exit", 0.6)],
        status="ok",
        cue_derivation_version="1",
    )
    return TrackMetadata(raw=raw, cues=cues)


def _lyrics() -> SyncedLyrics:
    return SyncedLyrics(
        source="ytmusic",
        verdict="matched",
        offset_applied_s=0.0,
        segments=[
            LyricSegment(1.2, 2.0, "first line", None),
            LyricSegment(1.8, 2.5, "second", None),
            LyricSegment(4.0, 5.0, "third", 0.9),
        ],
        lines_dropped=0,
        alignments=[],
        thresholds={},
    )


def test_row_count_and_grid_edges(track):
    timeline = build_per_second(track, _lyrics(), _meta())
    assert [r.t for r in timeline.rows] == list(range(10))  # floor(9.4) + 1
    outside = timeline.rows[0]
    assert (outside.bar, outside.energy_lufs, outside.rms, outside.chroma) == (
        None,
        None,
        None,
        None,
    )
    assert timeline.rows[5].bar is None  # t + 0.5 = 5.5 is past the last bar's end


def test_bar_mapping_scaling_and_chroma(track):
    rows = build_per_second(track, _lyrics(), _meta()).rows
    assert [rows[t].bar for t in (1, 2, 3, 4)] == [0, 0, 1, 1]
    assert rows[1].energy_lufs == -12.3
    assert (rows[1].rms, rows[3].rms) == (0.0, 1.0)
    assert rows[1].vocal == 0.0  # constant series
    assert (rows[1].chroma, rows[3].chroma) == ("C", "A")  # NNLSChroma bins start at A


def test_events_placed_in_their_second(track):
    rows = build_per_second(track, _lyrics(), _meta()).rows
    assert (rows[1].downbeat, rows[2].downbeat, rows[3].downbeat) == (1, 0, 1)
    assert rows[1].beats == 2
    assert rows[3].phrase == 1.23
    assert rows[3].cue == "hook_in;hook_exit"
    assert rows[1].cue == "first_downbeat"
    assert [rows[t].riser for t in (1, 2, 3, 4)] == [0, 1, 1, 0]
    assert rows[1].lyric == "first line;second"
    assert rows[4].lyric == "third"
    assert rows[2].lyric is None


def test_header_and_lyrics_table(track):
    timeline = build_per_second(track, _lyrics(), _meta())
    assert timeline.header.title == "Song"
    assert timeline.header.lufs_integrated == -9.0
    assert timeline.header.lyrics_source == "ytmusic"
    assert len(timeline.lyrics) == 3
