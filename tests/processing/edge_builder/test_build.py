import pytest

from processing.edge_builder.build import build_edges
from processing.edge_builder.config import EdgeBuilderConfig

DOWNBEATS = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]


def test_argmin_matches_hand_enumerated_grid(make_track, make_cue):
    """4-combo (2 cue_outs x 2 cue_ins), 1 enabled tier — worked by hand in the
    plan: hook_exit->intro_end (out1,in1) wins at cost 0.84, beating the other
    three combos (1.05, 1.05, 1.34) on cue_kind preference despite a tied energy
    delta with the (out2,in2) combo.
    """
    config = EdgeBuilderConfig(enabled_tiers=frozenset({3}))

    track_a = make_track(
        id="a",
        bpm=120.0,
        bpm_confidence=1.0,
        key="8A",
        key_confidence=1.0,
        structure_template="edm",
        downbeat_times=DOWNBEATS,
        energy_curve=[0.1, 0.2, 0.3, 0.4, 0.5],
        vocal_mask=[0.0, 0.0, 0.0, 0.0, 0.0],
        phrase_grid=[],
        cue_outs=[
            make_cue(position=1.0, kind="hook_exit", confidence=1.0),
            make_cue(position=9.0, kind="time_boxed", confidence=1.0),
        ],
        cue_ins=[],
        status="ok",
    )
    track_b = make_track(
        id="b",
        bpm=120.0,
        bpm_confidence=1.0,
        key="8A",
        key_confidence=1.0,
        structure_template="edm",
        downbeat_times=DOWNBEATS,
        energy_curve=[0.5, 0.4, 0.3, 0.2, 0.1],
        vocal_mask=[0.0, 0.0, 0.0, 0.0, 0.0],
        phrase_grid=[],
        cue_ins=[
            make_cue(position=1.0, kind="intro_end", confidence=1.0),
            make_cue(position=9.0, kind="first_downbeat", confidence=1.0),
        ],
        cue_outs=[],
        status="ok",
    )

    scored = build_edges([track_a, track_b], config)

    assert ("a", "b") in scored.edges
    edge = scored.edges[("a", "b")]

    # Stored plan corresponds to the winning (cue_out, cue_in, tier) combination.
    assert edge.plan.cue_out == pytest.approx(1.0)
    assert edge.plan.cue_in == pytest.approx(1.0)
    assert edge.plan.strategy_tier == 3

    assert edge.terms.tempo == pytest.approx(0.0)
    assert edge.terms.key == pytest.approx(0.0)
    assert edge.terms.energy == pytest.approx(0.4 / 6.0)
    assert edge.terms.vocal == pytest.approx(0.0)
    assert edge.terms.cue_kind == pytest.approx(0.0)
    assert edge.terms.phrase == pytest.approx(1.0)
    assert edge.terms.tier_penalty == pytest.approx(0.30)

    expected_cost = (
        config.w_tempo * edge.terms.tempo
        + config.w_key * edge.terms.key
        + config.w_energy * edge.terms.energy
        + config.w_vocal * edge.terms.vocal
        + config.w_cue_kind * edge.terms.cue_kind
        + config.w_phrase * edge.terms.phrase
        + edge.terms.tier_penalty
    )
    assert edge.cost == pytest.approx(expected_cost)
    assert edge.cost == pytest.approx(0.84)


def test_pool_filtering_and_no_self_edges(make_track, make_cue):
    config = EdgeBuilderConfig()

    def cued_track(id, status="ok", downbeat_times=None, energy_curve=None, vocal_mask=None):
        return make_track(
            id=id,
            bpm=120.0,
            key="8A",
            structure_template="edm",
            downbeat_times=downbeat_times if downbeat_times is not None else DOWNBEATS,
            energy_curve=energy_curve if energy_curve is not None else [0.1, 0.2, 0.3, 0.4, 0.5],
            vocal_mask=vocal_mask if vocal_mask is not None else [0.0] * 5,
            phrase_grid=[],
            cue_outs=[make_cue(position=1.0, kind="hook_exit")],
            cue_ins=[make_cue(position=1.0, kind="intro_end")],
            status=status,
        )

    track_a = cued_track("a")
    track_b = cued_track("b")
    excluded = cued_track("excluded", status="excluded")
    barless = cued_track("barless", downbeat_times=[0.0], energy_curve=[], vocal_mask=[])

    scored = build_edges([track_a, track_b, excluded, barless], config)

    assert ("a", "b") in scored.edges
    assert ("b", "a") in scored.edges
    assert ("a", "a") not in scored.edges
    assert ("b", "b") not in scored.edges
    assert all("excluded" not in key for key in scored.edges)
    assert all("barless" not in key for key in scored.edges)


def test_no_entry_when_a_side_has_no_cues(make_track, make_cue):
    config = EdgeBuilderConfig()

    track_a = make_track(id="a", downbeat_times=DOWNBEATS, cue_outs=[], cue_ins=[])
    track_b = make_track(
        id="b",
        downbeat_times=DOWNBEATS,
        cue_outs=[make_cue(position=1.0, kind="hook_exit")],
        cue_ins=[make_cue(position=1.0, kind="intro_end")],
    )

    scored = build_edges([track_a, track_b], config)

    # a -> b: a has no cue_outs, so no entry.
    assert ("a", "b") not in scored.edges
    # b -> a: b has cue_outs, but a has no cue_ins, so still no entry.
    assert ("b", "a") not in scored.edges


def test_no_entry_when_every_tier_is_ineligible(make_track, make_cue):
    config = EdgeBuilderConfig(enabled_tiers=frozenset({2}), tier2_max_bpm_ratio=0.03)

    track_a = make_track(
        id="a",
        bpm=100.0,
        downbeat_times=DOWNBEATS,
        cue_outs=[make_cue(position=1.0, kind="hook_exit")],
        cue_ins=[],
    )
    track_b = make_track(
        id="b",
        bpm=200.0,  # wildly outside tier2_max_bpm_ratio, and tier 2 is the only enabled tier
        downbeat_times=DOWNBEATS,
        cue_outs=[],
        cue_ins=[make_cue(position=1.0, kind="intro_end")],
    )

    scored = build_edges([track_a, track_b], config)
    assert ("a", "b") not in scored.edges
