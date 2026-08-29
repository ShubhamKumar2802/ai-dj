import pytest

from processing.path_search.config import PathSearchConfig
from processing.path_search.energy_arc import target_curve
from processing.path_search.objective import objective_terms, score_path, total
from processing.path_search.schema import ObjectiveTerms

# The inverted-arc path is deliberately ~2 edge-units CHEAPER on Sigma edge_costs
# (nearest-neighbour edges are always the cheapest, and they produce a flat or
# inverted arc). The arc term only rescues the good path if lambda is large.
_PERFECT = ObjectiveTerms(
    edges_total=20.0,
    arc_deviation=0.0,
    diversity_penalty=0.5,
    familiarity_deficit=0.5,
    boundary=0.5,
)
_INVERTED = ObjectiveTerms(
    edges_total=18.0,
    arc_deviation=0.6,
    diversity_penalty=0.5,
    familiarity_deficit=0.5,
    boundary=0.5,
)


def test_perfect_arc_wins_at_default_weights():
    config = PathSearchConfig()
    assert total(_PERFECT, config) < total(_INVERTED, config)


def test_scale_trap_regression_documents_why_lambda_is_not_one():
    # With w_arc left at 1.0 the cheaper-but-boring inverted-arc path wins — the
    # exact silent failure spec §4's edge-cost-unit weights guard against.
    config = PathSearchConfig(w_arc=1.0)
    assert total(_PERFECT, config) > total(_INVERTED, config)


def test_total_is_the_weighted_five_term_sum():
    config = PathSearchConfig()
    expected = 20.0 + 8.0 * 0.0 + 4.0 * 0.5 + 8.0 * 0.5 + 4.0 * 0.5
    assert total(_PERFECT, config) == pytest.approx(expected)


def test_objective_terms_recompute_the_four_path_level_terms():
    config = PathSearchConfig()
    k_eff = 6
    # Energy norms that trace the final-K_eff target exactly -> arc_deviation 0.
    norms = list(target_curve(k_eff, config))[:4]
    terms = objective_terms(
        path_energy_norms=norms,
        path_bpms=[120.0, 124.0, 128.0, 132.0],
        path_keys=["8A", "9A", "10A", "11A"],
        path_familiarities=[0.5, 0.5, 0.5, 0.5],
        opener_boundary_cost=0.0,
        closer_boundary_cost=1.0,
        edges_total=7.5,
        k_eff=k_eff,
        config=config,
    )
    assert terms.edges_total == 7.5
    assert terms.arc_deviation == pytest.approx(0.0)
    assert terms.familiarity_deficit == pytest.approx(0.5)
    assert terms.boundary == pytest.approx(0.5)
    assert 0.0 <= terms.diversity_penalty <= 1.0


def test_score_path_returns_total_of_its_own_terms():
    config = PathSearchConfig()
    args = dict(
        path_energy_norms=[0.3, 0.6, 0.9],
        path_bpms=[120.0, 125.0, 130.0],
        path_keys=["8A", "9A", "10A"],
        path_familiarities=[0.5, 0.5, 0.5],
        opener_boundary_cost=0.5,
        closer_boundary_cost=1.0,
        edges_total=3.0,
        k_eff=5,
        config=config,
    )
    score, terms = score_path(**args)
    assert score == pytest.approx(total(terms, config))
