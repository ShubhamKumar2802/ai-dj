from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.hook import detect_hook
from ingestion.cue_derivation.schema import PhraseBoundary

# 0.95 is chosen so the percentile threshold reliably lands within these
# fixtures' minority "high" block regardless of the exact high/low bar
# ratio each test uses (all well under 95% high) — not meant to reflect the
# production default of 0.5 (spec's ## Amendments already caveats that
# default as untuned against a representative corpus).
_ISOLATING_PERCENTILE = 0.95


def test_finds_plateau_and_one_exit_candidate_in_window(make_per_bar_features, make_raw_features):
    # 8 low bars, an 8-bar high plateau, 8 low bars again.
    n = 8
    per_bar = make_per_bar_features(n_bars=3 * n, bpm=120.0)
    energy = [-20.0] * n + [-5.0] * n + [-20.0] * n
    vocal = [10.0] * n + [80.0] * n + [10.0] * n
    raw = make_raw_features(per_bar, bpm=120.0, energy_curve=energy, vocal_band_energy=vocal)
    config = CueDerivationConfig(
        hook_high_energy_percentile=_ISOLATING_PERCENTILE,
        hook_high_vocal_percentile=_ISOLATING_PERCENTILE,
        # occupancy=1.0 makes plateau detection deterministic (only the
        # exact full-high window qualifies) so this test isolates the
        # exit-window logic; occupancy tolerance is its own test.
        hook_plateau_occupancy=1.0,
    )
    boundary_position = per_bar[2 * n].start_time  # where the plateau ends
    phrase_grid = [
        PhraseBoundary(position=boundary_position, strength=1.0, bars_since_previous=None)
    ]

    hook_in, hook_exit_candidates = detect_hook(raw, phrase_grid, config)

    assert hook_in == per_bar[n].start_time
    assert hook_exit_candidates == [boundary_position]


def test_every_boundary_within_time_box_bars_becomes_a_candidate(
    make_per_bar_features, make_raw_features
):
    # 2026-09-17 amendment (spec §6): no single "winner", no per-boundary drop
    # check — every phrase boundary from the plateau's end up to
    # time_box_bars past it is a candidate. Reuses time_box_bars rather than
    # a new constant (see hook.py's own comment for why an unbounded search
    # was tried and rejected: on a real track it picked a candidate 95%
    # through the whole file). Ranking which candidate is actually clean is
    # edge_builder's job.
    n = 8
    per_bar = make_per_bar_features(n_bars=100, bpm=120.0)
    energy = [-20.0] * n + [-5.0] * n + [-5.0] * (100 - 2 * n)
    vocal = [10.0] * n + [80.0] * n + [80.0] * (100 - 2 * n)
    raw = make_raw_features(per_bar, bpm=120.0, energy_curve=energy, vocal_band_energy=vocal)
    config = CueDerivationConfig(
        hook_high_energy_percentile=_ISOLATING_PERCENTILE,
        hook_high_vocal_percentile=_ISOLATING_PERCENTILE,
        hook_plateau_occupancy=1.0,
        time_box_bars=32,
    )
    plateau_end_time = per_bar[2 * n].start_time  # bar 16

    in_window = [
        plateau_end_time,  # exactly at the window's start — included
        per_bar[2 * n + 1].start_time,  # 1 bar past
        per_bar[2 * n + 31].start_time,  # bar 47 — 31 bars past, still inside
    ]
    past_window = per_bar[2 * n + 32].start_time  # bar 48 — exactly 32 bars past, excluded
    phrase_grid = [
        PhraseBoundary(position=p, strength=1.0, bars_since_previous=None)
        for p in [*in_window, past_window]
    ]

    _, hook_exit_candidates = detect_hook(raw, phrase_grid, config)

    assert hook_exit_candidates == in_window


def test_boundary_before_plateau_end_is_not_a_candidate(make_per_bar_features, make_raw_features):
    n = 8
    per_bar = make_per_bar_features(n_bars=3 * n, bpm=120.0)
    energy = [-20.0] * n + [-5.0] * n + [-20.0] * n
    vocal = [10.0] * n + [80.0] * n + [10.0] * n
    raw = make_raw_features(per_bar, bpm=120.0, energy_curve=energy, vocal_band_energy=vocal)
    config = CueDerivationConfig(
        hook_high_energy_percentile=_ISOLATING_PERCENTILE,
        hook_high_vocal_percentile=_ISOLATING_PERCENTILE,
        hook_plateau_occupancy=1.0,
    )
    # Inside the plateau itself, one bar before it ends — must not appear.
    mid_plateau = per_bar[n + 3].start_time
    phrase_grid = [PhraseBoundary(position=mid_plateau, strength=1.0, bars_since_previous=None)]

    _, hook_exit_candidates = detect_hook(raw, phrase_grid, config)

    assert hook_exit_candidates == []


def test_plateau_at_track_end_has_no_exit_candidates(make_per_bar_features, make_raw_features):
    n = 8
    per_bar = make_per_bar_features(n_bars=2 * n, bpm=120.0)
    energy = [-20.0] * n + [-5.0] * n
    vocal = [10.0] * n + [80.0] * n
    raw = make_raw_features(per_bar, bpm=120.0, energy_curve=energy, vocal_band_energy=vocal)
    config = CueDerivationConfig(
        hook_high_energy_percentile=_ISOLATING_PERCENTILE,
        hook_high_vocal_percentile=_ISOLATING_PERCENTILE,
        hook_plateau_occupancy=1.0,
    )

    hook_in, hook_exit_candidates = detect_hook(raw, phrase_grid=[], config=config)

    assert hook_in == per_bar[n].start_time
    assert hook_exit_candidates == []


def test_plateau_occupancy_tolerates_one_bar_dip(make_per_bar_features, make_raw_features):
    n = 8
    per_bar = make_per_bar_features(n_bars=3 * n, bpm=120.0)
    high_energy = [-5.0] * n
    high_energy[4] = -20.0  # a single dip (a breath, a quiet fill) inside the plateau
    high_vocal = [80.0] * n
    high_vocal[4] = 10.0
    energy = [-20.0] * n + high_energy + [-20.0] * n
    vocal = [10.0] * n + high_vocal + [10.0] * n
    raw = make_raw_features(per_bar, bpm=120.0, energy_curve=energy, vocal_band_energy=vocal)
    config = CueDerivationConfig(
        hook_high_energy_percentile=_ISOLATING_PERCENTILE,
        hook_high_vocal_percentile=_ISOLATING_PERCENTILE,
        # 0.8 (not the production default 0.7) is chosen so exactly the
        # intended 7-of-8 dip window qualifies, and no partial-overlap
        # window bordering it also qualifies — isolates the "one dip is
        # tolerated" property this test targets.
        hook_plateau_occupancy=0.8,
    )

    hook_in, _ = detect_hook(raw, phrase_grid=[], config=config)

    assert hook_in == per_bar[n].start_time


def test_no_plateau_when_high_region_is_too_short(make_per_bar_features, make_raw_features):
    n = 8
    short = 4  # well under hook_min_bars=8; even full window overlap only reaches 4/8=0.5
    per_bar = make_per_bar_features(n_bars=2 * n + short, bpm=120.0)
    energy = [-20.0] * n + [-5.0] * short + [-20.0] * n
    vocal = [10.0] * n + [80.0] * short + [10.0] * n
    raw = make_raw_features(per_bar, bpm=120.0, energy_curve=energy, vocal_band_energy=vocal)
    config = CueDerivationConfig(
        hook_high_energy_percentile=_ISOLATING_PERCENTILE,
        hook_high_vocal_percentile=_ISOLATING_PERCENTILE,
    )

    hook_in, hook_exit_candidates = detect_hook(raw, phrase_grid=[], config=config)

    assert hook_in is None
    assert hook_exit_candidates == []
