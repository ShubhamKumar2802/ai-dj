from dataclasses import dataclass
from typing import Literal

from common.contracts.schema import MixPlan


@dataclass
class ObjectiveTerms:
    # Every field is in [0,1] EXCEPT edges_total, which is a sum over K-1 edges
    # and is deliberately not normalised (spec §4).
    edges_total: float
    arc_deviation: float
    diversity_penalty: float
    familiarity_deficit: float
    boundary: float


@dataclass
class SearchDiagnostics:
    # D21's "still log total duration"; design-v3 §9's objective evaluation metrics.
    total_cost: float
    objective: ObjectiveTerms
    # == len(plan.tracks). Less than the requested track_count means the pool
    # dead-ended (D21) — a degradation to report, not an error.
    achieved_track_count: int
    # D21 — logged, never constrained (spec §10).
    estimated_duration_s: float
    # strategy_tier -> count. D5's "% at tier 2 is the best single health metric".
    tier_histogram: dict[int, int]
    # Nodes surviving the pool filter (spec §3).
    pool_size: int
    # D7 quarantine, design-v3 §9.
    excluded_count: int
    cut_only_count: int
    # Totals of the paths behind the winner, in the winner's length cohort.
    runner_up_costs: list[float]
    terminated_on: Literal["k_reached", "pool_exhausted"]


@dataclass
class PathSearchResult:
    plan: MixPlan
    diagnostics: SearchDiagnostics
    # The next-best complete paths, in cost order. Empty unless
    # PathSearchConfig.n_alternatives > 0. These are beam neighbours and share
    # long prefixes with the winner (spec Q12).
    alternatives: list[MixPlan]


class NoViablePathError(Exception):
    """No two-track chain exists at all.

    Raised when the pool filter (spec §3) leaves fewer than two viable tracks, or
    when the beam produces no path of length >= 2. Raised loudly rather than
    returning a degenerate one-track plan the renderer would then assert on.
    """
