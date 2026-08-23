from dataclasses import dataclass

from common.contracts.schema import Junction


@dataclass
class CostTerms:
    tempo: float
    key: float
    energy: float
    vocal: float
    cue_kind: float
    phrase: float
    tier_penalty: float


@dataclass
class ScoredEdge:
    from_track: str
    to_track: str
    cost: float
    plan: Junction
    terms: CostTerms


@dataclass
class ScoredEdges:
    edges: dict[tuple[str, str], ScoredEdge]
