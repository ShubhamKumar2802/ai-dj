from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.cues import emit_cues
from ingestion.cue_derivation.schema import Cue, PhraseBoundary
from ingestion.feature_extractor.schema import RiserCandidate


def test_edm_template_emits_riser_start_when_riser_precedes_grid_start(
    make_per_bar_features, make_raw_features
):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(
        per_bar,
        bpm=120.0,
        downbeat_confidence=0.7,
        riser_candidates=[RiserCandidate(start_time=1.0, resolution_time=3.5, confidence=0.9)],
    )

    cue_ins, _ = emit_cues(
        raw,
        grid_start=4.0,
        free_intro_end=1.0,
        structure_template="edm",
        hook_in=None,
        hook_exit=None,
        phrase_grid=[],
        config=CueDerivationConfig(),
    )

    assert cue_ins[0] == Cue(position=1.0, kind="riser_start", confidence=0.9)
    assert cue_ins[-1] == Cue(position=4.0, kind="first_downbeat", confidence=0.7)
    assert len(cue_ins) == 2


def test_edm_template_emits_intro_end_when_no_riser_precedes_grid_start(
    make_per_bar_features, make_raw_features
):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.7, riser_candidates=[])

    cue_ins, _ = emit_cues(
        raw,
        grid_start=4.0,
        free_intro_end=4.0,  # equals grid_start, per §3, when no riser precedes it
        structure_template="edm",
        hook_in=None,
        hook_exit=None,
        phrase_grid=[],
        config=CueDerivationConfig(),
    )

    assert cue_ins[0] == Cue(position=4.0, kind="intro_end", confidence=0.7)
    assert cue_ins[-1] == Cue(position=4.0, kind="first_downbeat", confidence=0.7)
    assert len(cue_ins) == 2  # same position, distinct kinds — intentional (spec §7 amendment)


def test_non_edm_template_emits_hook_in_when_found(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.7)

    cue_ins, _ = emit_cues(
        raw,
        grid_start=4.0,
        free_intro_end=4.0,
        structure_template="film",
        hook_in=10.0,
        hook_exit=None,
        phrase_grid=[],
        config=CueDerivationConfig(),
    )

    assert cue_ins[0] == Cue(position=10.0, kind="hook_in", confidence=0.5)
    assert cue_ins[-1] == Cue(position=4.0, kind="first_downbeat", confidence=0.7)
    assert len(cue_ins) == 2


def test_non_edm_template_without_hook_in_only_emits_fallback(
    make_per_bar_features, make_raw_features
):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.7)

    cue_ins, _ = emit_cues(
        raw,
        grid_start=4.0,
        free_intro_end=4.0,
        structure_template="unknown",
        hook_in=None,
        hook_exit=None,
        phrase_grid=[],
        config=CueDerivationConfig(),
    )

    assert cue_ins == [Cue(position=4.0, kind="first_downbeat", confidence=0.7)]


def test_hard_constraint_drops_non_riser_cue_before_grid_start(
    make_per_bar_features, make_raw_features
):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.7, riser_candidates=[])

    # Deliberately inconsistent input (free_intro_end < grid_start with no
    # riser) — exercises the hard-constraint filter itself generically,
    # not just via the riser_start exemption a legitimate caller would hit.
    cue_ins, _ = emit_cues(
        raw,
        grid_start=4.0,
        free_intro_end=1.0,
        structure_template="edm",
        hook_in=None,
        hook_exit=None,
        phrase_grid=[],
        config=CueDerivationConfig(),
    )

    assert cue_ins == [Cue(position=4.0, kind="first_downbeat", confidence=0.7)]


def test_hook_exit_included_in_cue_outs_when_present(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.7)

    _, cue_outs = emit_cues(
        raw,
        grid_start=0.0,
        free_intro_end=0.0,
        structure_template="unknown",
        hook_in=None,
        hook_exit=20.0,
        phrase_grid=[],
        config=CueDerivationConfig(),
    )

    assert cue_outs == [Cue(position=20.0, kind="hook_exit", confidence=0.5)]


def test_time_boxed_fallback_present_past_time_box_bars(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.7)
    config = CueDerivationConfig()
    # bars_to_seconds(32, bpm=120, beats_per_bar=4) == 64.0
    phrase_grid = [PhraseBoundary(position=70.0, strength=1.0, bars_since_previous=None)]

    _, cue_outs = emit_cues(
        raw,
        grid_start=0.0,
        free_intro_end=0.0,
        structure_template="unknown",
        hook_in=None,
        hook_exit=None,
        phrase_grid=phrase_grid,
        config=config,
    )

    assert cue_outs == [Cue(position=70.0, kind="time_boxed", confidence=0.3)]


def test_no_time_boxed_fallback_when_no_boundary_clears_time_box(
    make_per_bar_features, make_raw_features
):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.7)
    phrase_grid = [PhraseBoundary(position=10.0, strength=1.0, bars_since_previous=None)]

    _, cue_outs = emit_cues(
        raw,
        grid_start=0.0,
        free_intro_end=0.0,
        structure_template="unknown",
        hook_in=None,
        hook_exit=None,
        phrase_grid=phrase_grid,
        config=CueDerivationConfig(),
    )

    assert cue_outs == []


def test_time_boxed_anchors_to_post_filter_cue_in(make_per_bar_features, make_raw_features):
    per_bar = make_per_bar_features(n_bars=8, bpm=120.0)
    raw = make_raw_features(per_bar, bpm=120.0, downbeat_confidence=0.7, riser_candidates=[])
    # time_box_bars=32 bars @ 120bpm/4-per-bar = 64.0s.
    # old (buggy) anchor = -10.0 (the dropped intro_end) -> target 54.0
    #   -> would have picked the 60.0 boundary
    # new (fixed) anchor = grid_start = 4.0 -> target 68.0
    #   -> correctly picks the 70.0 boundary
    phrase_grid = [
        PhraseBoundary(position=60.0, strength=1.0, bars_since_previous=None),
        PhraseBoundary(position=70.0, strength=1.0, bars_since_previous=None),
    ]

    _, cue_outs = emit_cues(
        raw,
        grid_start=4.0,
        free_intro_end=-10.0,  # deliberately before grid_start -> intro_end cue gets filtered out
        structure_template="edm",
        hook_in=None,
        hook_exit=None,
        phrase_grid=phrase_grid,
        config=CueDerivationConfig(),
    )

    assert cue_outs == [Cue(position=70.0, kind="time_boxed", confidence=0.3)]
