from collections.abc import Sequence

from processing.path_search.config import PathSearchConfig
from processing.path_search.diversity import diversity_penalty
from processing.path_search.energy_arc import arc_deviation
from processing.path_search.familiarity import familiarity_deficit
from processing.path_search.schema import ObjectiveTerms


def objective_terms(
    path_energy_norms: Sequence[float],
    path_bpms: Sequence[float],
    path_keys: Sequence[str | None],
    path_familiarities: Sequence[float],
    opener_boundary_cost: float,
    closer_boundary_cost: float,
    edges_total: float,
    k_eff: int,
    config: PathSearchConfig,
) -> ObjectiveTerms:
    """The five-term breakdown for a partial OR complete path (spec §4).

    The four path-level terms recompute over the whole ``<= k_eff`` path each
    call; ``edges_total`` is passed in because the beam accumulates it
    incrementally (one addition per extension). ``boundary`` is the mean of two
    precomputed pool-index scalars — the closer half is evaluated on the frontier
    track at every step, which is only the *real* closer once a path is complete
    (spec Q13; moot in v1 while ``closer_cost`` is a constant).
    """
    return ObjectiveTerms(
        edges_total=edges_total,
        arc_deviation=arc_deviation(path_energy_norms, k_eff, config),
        diversity_penalty=diversity_penalty(path_bpms, path_keys, k_eff, config),
        familiarity_deficit=familiarity_deficit(path_familiarities),
        boundary=0.5 * (opener_boundary_cost + closer_boundary_cost),
    )


def total(terms: ObjectiveTerms, config: PathSearchConfig) -> float:
    """``Sigma edge_costs + lambda*arc + mu*diversity + nu*familiarity + beta*boundary``.

    The weights are in EDGE-COST units (spec §4's scale fix). ``Sigma edge_costs``
    is a sum over K-1 edges landing around 15-25 while every path-level term caps
    at 1.0, so naive weights of 1.0 would make three of the five terms silently
    inert — a failure that still produces plausible-looking setlists. ``w_arc =
    8.0`` instead reads as "a wholly wrong energy arc costs as much as eight
    typical junctions".
    """
    return (
        terms.edges_total
        + config.w_arc * terms.arc_deviation
        + config.w_diversity * terms.diversity_penalty
        + config.w_familiarity * terms.familiarity_deficit
        + config.w_boundary * terms.boundary
    )


def score_path(
    path_energy_norms: Sequence[float],
    path_bpms: Sequence[float],
    path_keys: Sequence[str | None],
    path_familiarities: Sequence[float],
    opener_boundary_cost: float,
    closer_boundary_cost: float,
    edges_total: float,
    k_eff: int,
    config: PathSearchConfig,
) -> tuple[float, ObjectiveTerms]:
    """``(total, ObjectiveTerms)`` for a path — the beam calls this once per
    survivor per step."""
    terms = objective_terms(
        path_energy_norms,
        path_bpms,
        path_keys,
        path_familiarities,
        opener_boundary_cost,
        closer_boundary_cost,
        edges_total,
        k_eff,
        config,
    )
    return total(terms, config), terms
