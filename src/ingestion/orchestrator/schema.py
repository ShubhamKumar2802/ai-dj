from dataclasses import dataclass
from typing import Literal

from ingestion.cue_derivation.schema import Cue, PhraseBoundary


@dataclass
class Track:
    id: str
    path: str
    content_hash: str
    duration: float
    sample_rate: int

    bpm: float
    bpm_confidence: float
    beat_times: list[float]
    downbeat_times: list[float]
    downbeat_confidence: float
    beats_per_bar: int

    grid_start: float
    grid_confidence: float
    free_intro_end: float

    phrase_length_bars: float | None
    phrase_grid: list[PhraseBoundary]

    key: str | None
    key_confidence: float | None

    lufs_integrated: float
    true_peak: float

    energy_curve: list[float]
    vocal_mask: list[float]

    structure_template: Literal["edm", "film", "unknown"]

    cue_ins: list[Cue]
    cue_outs: list[Cue]

    familiarity_score: float | None
    era: str | None
    is_club_edit: bool | None

    analysis_version: str
    status: Literal["ok", "cut_only", "excluded"]


@dataclass
class IngestionFailure:
    path: str
    error: str
    error_type: str


@dataclass
class IngestionResult:
    tracks: list[Track]
    failures: list[IngestionFailure]
