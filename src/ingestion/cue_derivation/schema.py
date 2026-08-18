from dataclasses import dataclass
from typing import Literal

CueKind = Literal[
    "first_downbeat",
    "intro_end",
    "chorus_start",
    "chorus_end",
    "interlude_start",
    "outro_start",
    "riser_start",
    "hook_in",
    "hook_exit",
    "time_boxed",
]


@dataclass
class PhraseBoundary:
    position: float
    strength: float
    bars_since_previous: float | None


@dataclass
class Cue:
    position: float
    kind: CueKind
    confidence: float


@dataclass
class CueDerivationResult:
    grid_start: float
    grid_confidence: float
    free_intro_end: float

    phrase_length_bars: float | None
    phrase_grid: list[PhraseBoundary]

    structure_template: Literal["edm", "film", "unknown"]

    cue_ins: list[Cue]
    cue_outs: list[Cue]

    status: Literal["ok", "cut_only", "excluded"]
    cue_derivation_version: str
