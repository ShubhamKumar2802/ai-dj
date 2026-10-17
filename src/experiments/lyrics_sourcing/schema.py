"""Every inter-step data contract (spec §5).

All times are float seconds (design-v3 D20) unless noted. Dataclasses throughout, except the
LLM output schema, which is pydantic because `llm_service` requires it.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from ingestion.cue_derivation.schema import CueDerivationResult
from ingestion.feature_extractor.schema import RawFeatures

CandidateStatus = Literal["synced", "plain_only", "not_found", "error"]
AlignmentVerdict = Literal["matched", "offset_corrected", "rejected", "unverifiable"]
LyricsVerdict = Literal["matched", "offset_corrected", "unverifiable", "fallback"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StepError(Exception):
    """A step failed; the run stops and every earlier step's output stays on disk (§4.8)."""

    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"[{step}] {message}")
        self.step = step
        self.message = message


# --- step 1: ingest -------------------------------------------------------------------


@dataclass
class IngestedTrack:
    video_id: str
    url: str
    path: str  # audio file path, relative to the repo root
    content_hash: str  # ingestion.feature_extractor.content_hash.hash_file(path)
    duration: float  # from yt-dlp
    raw_title: str  # the video title
    title: str | None  # yt-dlp `track`
    artist: str | None  # yt-dlp `artists[0]` / `artist` / `creator`
    album: str | None


# --- step 2: lyrics -------------------------------------------------------------------


@dataclass
class LyricLine:
    start: float  # relative to the lyrics' own recording
    end: float | None  # next line's start (LRC) or the source's own end; None if unknown
    text: str


@dataclass
class LyricsCandidate:
    source: str  # fetcher name, e.g. "ytmusic" | "lrclib"
    source_ref: str | None  # ytmusic browseId / lrclib record id
    status: CandidateStatus
    lines: list[LyricLine]  # non-empty iff status == "synced"
    plain_text: str | None
    reference_duration: float | None  # duration of the recording the lyrics were timed to
    error: str | None
    fetched_at: str  # ISO-8601 UTC


@dataclass
class LyricsFetchResult:
    candidates: list[LyricsCandidate]  # in lyrics.impl (priority) order


# --- step 3a: transcribe --------------------------------------------------------------


@dataclass
class Word:
    text: str
    start: float
    end: float
    probability: float | None


@dataclass
class Segment:
    text: str
    start: float
    end: float
    words: list[Word]


@dataclass
class Transcript:
    language: str | None
    segments: list[Segment]  # time-ordered
    whisper_config_id: str
    model: str


# --- step 3b: time_match --------------------------------------------------------------


@dataclass
class Alignment:  # one per synced candidate
    source: str
    verdict: AlignmentVerdict
    offset_s: float | None
    anchorable_lines: int
    inlier_lines: int
    line_coverage: float | None
    median_abs_residual_s: float | None
    drift_slope: float | None
    transcript_density_wpm: float
    urdu_script_words: int


@dataclass
class LyricSegment:  # same shape as 04_transcription.md §3.3's draft
    start: float
    end: float
    text: str
    confidence: float | None


@dataclass
class SyncedLyrics:
    source: str  # winning fetcher name, or "whisper"
    verdict: LyricsVerdict
    offset_applied_s: float
    segments: list[LyricSegment]
    lines_dropped: int
    alignments: list[Alignment]
    thresholds: dict[str, float]  # the time_match config in force


# --- step 4: metadata -----------------------------------------------------------------


@dataclass
class TrackMetadata:
    raw: RawFeatures
    cues: CueDerivationResult


# --- step 5: timeline -----------------------------------------------------------------


@dataclass
class TimelineHeader:  # field order == serialized order (§4.6)
    title: str | None
    artist: str | None
    video_id: str
    duration: float
    bpm: float | None
    bpm_confidence: float | None
    key: str | None
    key_confidence: float | None
    lufs_integrated: float | None
    true_peak: float | None
    structure_template: str | None
    grid_start: float | None
    phrase_length_bars: float | None
    cue_status: str | None
    lyrics_source: str | None
    lyrics_verdict: str | None
    lyrics_offset_s: float | None


@dataclass
class TimelineRow:  # field order == column order (§4.6)
    t: int
    bar: int | None
    downbeat: int | None
    beats: int | None
    energy_lufs: float | None
    vocal: float | None
    rms: float | None
    low: float | None
    high: float | None
    centroid: float | None
    flux: float | None
    chroma: str | None
    phrase: float | None
    cue: str | None
    riser: int | None
    lyric: str | None


@dataclass
class Timeline:
    header: TimelineHeader
    rows: list[TimelineRow]
    lyrics: list[LyricSegment]


# --- step 6: llm (pydantic: the model sees every Field description) --------------------

SectionType = Literal[
    "intro",
    "verse",
    "pre_chorus",
    "chorus_or_hook",
    "bridge",
    "interlude",
    "instrumental",
    "outro",
]


class LabeledSection(BaseModel):
    type: SectionType = Field(description="Section label.")
    start: int = Field(description="Start second; must be a `t` value from the timeline.")
    end: int = Field(description="End second (exclusive); must be a `t` value from the timeline.")
    confidence: float = Field(ge=0, le=1, description="How sure you are of this label, 0-1.")
    evidence: str = Field(description="Short justification citing columns and/or lyrics.")


class HookWindow(BaseModel):
    start: int = Field(description="Hook start second; a `t` value from the timeline.")
    end: int = Field(description="Hook end second; a `t` value from the timeline.")
    reason: str = Field(description="Why this is the most recognisable, repeatable passage.")


class StructureLabels(BaseModel):
    sections: list[LabeledSection] = Field(
        description="Consecutive sections covering the whole song, in time order."
    )
    hook: HookWindow = Field(description="The single best hook window for a DJ to cut to.")
    notes: str = Field(description="Anything uncertain or notable about the structure.")


@dataclass
class StructureResult:
    labels: StructureLabels  # after validate()'s clamp/sort
    issues: list[str]
    model: str
    prompt_version: str
    estimated_tokens: int
    serializer: str  # "toon" | "json"


# --- run --------------------------------------------------------------------------------


@dataclass
class RunSummary:
    video_id: str
    steps_run: list[str]
    steps_reloaded: list[str]
    config: dict  # ExperimentConfig.model_dump()
    started_at: str
    finished_at: str
