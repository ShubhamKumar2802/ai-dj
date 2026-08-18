from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.derive import derive_cues
from ingestion.cue_derivation.schema import Cue, CueDerivationResult, PhraseBoundary


def test_derive_cues_returns_fully_populated_result(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=24, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.5)
    config = CueDerivationConfig()

    result = derive_cues(raw, config)

    assert isinstance(result, CueDerivationResult)
    assert result.grid_start == raw.downbeat_times[0]
    assert result.grid_confidence == 0.5
    assert isinstance(result.phrase_grid, list)
    assert all(isinstance(b, PhraseBoundary) for b in result.phrase_grid)
    assert result.structure_template in ("edm", "film", "unknown")
    assert isinstance(result.cue_ins, list) and len(result.cue_ins) >= 1
    assert isinstance(result.cue_outs, list)
    assert all(isinstance(c, Cue) for c in result.cue_ins + result.cue_outs)
    assert result.status == "ok"  # 0.5 clears both amended thresholds (0.01/0.15)
    assert result.cue_derivation_version == config.cue_derivation_version


def test_derive_cues_handles_empty_downbeat_times_without_crashing(
    make_per_bar_features, make_raw_features
):
    per_bar = make_per_bar_features(n_bars=24, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.0, downbeat_times=[])
    config = CueDerivationConfig()

    result = derive_cues(raw, config)

    assert result.grid_start == 0.0
    assert result.free_intro_end == 0.0
    assert result.status == "excluded"


def test_cue_derivation_version_defaults_to_config_constant(
    make_per_bar_features, make_raw_features
):
    per_bar = make_per_bar_features(n_bars=24, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0)

    result = derive_cues(raw, CueDerivationConfig())

    from ingestion.cue_derivation.config import CUE_DERIVATION_VERSION

    assert result.cue_derivation_version == CUE_DERIVATION_VERSION
