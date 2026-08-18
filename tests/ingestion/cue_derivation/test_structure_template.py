from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.schema import PhraseBoundary
from ingestion.cue_derivation.structure_template import classify_structure_template


def _phrase_grid_from_gaps(gaps: list[float]) -> list[PhraseBoundary]:
    position = 0.0
    boundaries = []
    for gap in [None, *gaps]:
        boundaries.append(PhraseBoundary(position=position, strength=1.0, bars_since_previous=gap))
        position += 1.0
    return boundaries


def test_edm_like_signals_agree(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=1, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0)
    config = CueDerivationConfig()
    intro_threshold = config.edm_intro_bars_threshold * raw.beats_per_bar * 60.0 / raw.bpm
    free_intro_end = intro_threshold + 1.0  # clears threshold -> edm vote

    phrase_grid = _phrase_grid_from_gaps([8.0, 8.0, 8.0])  # perfectly regular -> edm vote

    assert classify_structure_template(raw, free_intro_end, phrase_grid, config) == "edm"


def test_film_like_signals_agree(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=1, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0)
    config = CueDerivationConfig()
    free_intro_end = 0.0  # below threshold -> film vote

    phrase_grid = _phrase_grid_from_gaps([6.0, 14.0, 9.0])  # irregular -> film vote

    assert classify_structure_template(raw, free_intro_end, phrase_grid, config) == "film"


def test_disagreeing_signals_yield_unknown(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=1, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0)
    config = CueDerivationConfig()
    intro_threshold = config.edm_intro_bars_threshold * raw.beats_per_bar * 60.0 / raw.bpm
    free_intro_end = intro_threshold + 1.0  # edm vote

    phrase_grid = _phrase_grid_from_gaps([6.0, 14.0, 9.0])  # film vote

    assert classify_structure_template(raw, free_intro_end, phrase_grid, config) == "unknown"


def test_regularity_signal_abstains_with_fewer_than_two_gaps(
    make_per_bar_features, make_raw_features
):
    per_bar = make_per_bar_features(n_bars=1, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0)
    config = CueDerivationConfig()
    free_intro_end = 0.0  # film vote, and the only vote since regularity abstains

    phrase_grid = _phrase_grid_from_gaps([8.0])  # only 1 gap -> abstain

    assert classify_structure_template(raw, free_intro_end, phrase_grid, config) == "film"
