from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.status import quarantine


def test_below_exclude_threshold_is_excluded():
    config = CueDerivationConfig(exclude_threshold=0.01, cut_only_threshold=0.15)

    assert quarantine(0.005, config) == "excluded"


def test_exactly_at_exclude_threshold_is_not_excluded():
    # Strict `<` comparison (spec §8) — equality does not quarantine.
    config = CueDerivationConfig(exclude_threshold=0.01, cut_only_threshold=0.15)

    assert quarantine(0.01, config) == "cut_only"


def test_between_thresholds_is_cut_only():
    config = CueDerivationConfig(exclude_threshold=0.01, cut_only_threshold=0.15)

    assert quarantine(0.05, config) == "cut_only"


def test_exactly_at_cut_only_threshold_is_ok():
    config = CueDerivationConfig(exclude_threshold=0.01, cut_only_threshold=0.15)

    assert quarantine(0.15, config) == "ok"


def test_above_cut_only_threshold_is_ok():
    config = CueDerivationConfig(exclude_threshold=0.01, cut_only_threshold=0.15)

    assert quarantine(0.79, config) == "ok"
