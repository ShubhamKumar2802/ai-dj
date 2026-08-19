from ingestion.cue_derivation.grid_origin import derive_grid_origin
from ingestion.feature_extractor.schema import RiserCandidate


def test_grid_start_is_first_detected_downbeat(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.5)

    grid_start, _, _ = derive_grid_origin(raw)

    assert grid_start == raw.downbeat_times[0]


def test_grid_confidence_is_passed_through_unchanged(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.234)

    _, grid_confidence, _ = derive_grid_origin(raw)

    assert grid_confidence == 0.234


def test_free_intro_end_equals_grid_start_with_no_riser(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, riser_candidates=[])

    grid_start, _, free_intro_end = derive_grid_origin(raw)

    assert free_intro_end == grid_start


def test_free_intro_end_uses_riser_start_when_riser_precedes_grid_start(
    make_per_bar_features, make_raw_features
):
    # start_offset=4.0 models a real free-time intro before the grid starts
    # (F3: unpulsed intros give onset detection nothing to fire on) — a
    # riser can only precede grid_start when grid_start isn't 0.0.
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0, start_offset=4.0)
    raw = make_raw_features(
        per_bar,
        bpm=120.0,
        riser_candidates=[RiserCandidate(start_time=1.0, resolution_time=3.9, confidence=0.8)],
    )
    assert raw.downbeat_times[0] == 4.0  # sanity: riser genuinely precedes grid_start

    _, _, free_intro_end = derive_grid_origin(raw)

    assert free_intro_end == 1.0


def test_riser_after_grid_start_does_not_affect_free_intro_end(
    make_per_bar_features, make_raw_features
):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0, start_offset=4.0)
    raw = make_raw_features(
        per_bar,
        bpm=120.0,
        riser_candidates=[RiserCandidate(start_time=5.0, resolution_time=5.9, confidence=0.8)],
    )
    grid_start = raw.downbeat_times[0]
    assert 5.0 > grid_start  # sanity: riser starts after grid_start, so it's irrelevant here

    _, _, free_intro_end = derive_grid_origin(raw)

    assert free_intro_end == grid_start


def test_empty_downbeat_times_returns_zeroed_grid_instead_of_crashing(
    make_per_bar_features, make_raw_features
):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.0, downbeat_times=[])

    grid_start, grid_confidence, free_intro_end = derive_grid_origin(raw)

    assert (grid_start, grid_confidence, free_intro_end) == (0.0, 0.0, 0.0)
