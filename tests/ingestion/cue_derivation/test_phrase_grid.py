from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.phrase_grid import detect_phrase_boundaries


def test_no_boundaries_on_flat_features(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=20, bpm=120.0)  # every field flat/boring
    raw = make_raw_features(per_bar, bpm=120.0)

    phrase_grid, phrase_length_bars = detect_phrase_boundaries(raw, CueDerivationConfig())

    assert phrase_grid == []
    assert phrase_length_bars is None


def test_detects_single_deliberate_boundary(make_per_bar_features, make_raw_features):
    n_before, n_after = 16, 16
    before = make_per_bar_features(
        n_bars=n_before, bpm=120.0, rms=[0.1] * n_before, spectral_centroid=[500.0] * n_before
    )
    after = make_per_bar_features(
        n_bars=n_after,
        bpm=120.0,
        start_offset=before[-1].end_time,
        rms=[0.4] * n_after,
        spectral_centroid=[2000.0] * n_after,
    )
    per_bar = before + after
    raw = make_raw_features(per_bar, bpm=120.0)

    phrase_grid, phrase_length_bars = detect_phrase_boundaries(raw, CueDerivationConfig())

    assert len(phrase_grid) == 1
    assert phrase_grid[0].position == per_bar[n_before].start_time
    assert phrase_length_bars is None  # advisory stat needs >=2 boundaries (spec §4)


def test_bars_since_previous_and_phrase_length_bars_with_two_boundaries(
    make_per_bar_features, make_raw_features
):
    n = 16
    block_a = make_per_bar_features(
        n_bars=n, bpm=120.0, rms=[0.1] * n, spectral_centroid=[500.0] * n
    )
    block_b = make_per_bar_features(
        n_bars=n,
        bpm=120.0,
        start_offset=block_a[-1].end_time,
        rms=[0.4] * n,
        spectral_centroid=[2000.0] * n,
    )
    block_c = make_per_bar_features(
        n_bars=n,
        bpm=120.0,
        start_offset=block_b[-1].end_time,
        rms=[0.1] * n,
        spectral_centroid=[500.0] * n,
    )
    per_bar = block_a + block_b + block_c
    raw = make_raw_features(per_bar, bpm=120.0)

    phrase_grid, phrase_length_bars = detect_phrase_boundaries(raw, CueDerivationConfig())

    assert len(phrase_grid) == 2
    assert phrase_grid[0].bars_since_previous is None
    assert phrase_grid[1].bars_since_previous == 16.0
    assert phrase_length_bars == 16.0
