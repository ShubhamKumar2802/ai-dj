"""Data shapes: the LLM's answer (pydantic, because `llm_service` requires it) and the
plain dataclasses the rest of the experiment passes around."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Technique = Literal["cut", "bass_swap", "echo_out", "filter_fade", "other"]


class TransitionAnswer(BaseModel):
    """What the LLM must return for one pair. Bars are the answer; the mm:ss strings are
    only a cross-check against the bar's real start time."""

    model_config = ConfigDict(extra="forbid")

    exit_bar_a: int = Field(description="Bar number in track A where A ends (cut point)")
    exit_time_a: str = Field(description="mm:ss of that bar, as read off A's time axis")
    entry_bar_b: int = Field(description="Bar number in track B where B starts playing")
    entry_time_b: str = Field(description="mm:ss of that bar, as read off B's time axis")
    technique: Technique = Field(description="Transition technique you would use")
    length_bars: int = Field(ge=0, description="Length of that transition in bars (0 = cut)")
    reasoning: str = Field(description="Why these two points and this technique")
    notes_a: str = Field(description="What you see in track A's waveform, section by section")
    notes_b: str = Field(description="What you see in track B's waveform, section by section")


@dataclass
class TrackFacts:
    """One track's measured facts, from the cached feature extractor."""

    label: Literal["A", "B"]
    name: str
    path: str
    duration: float
    bpm: float
    lufs: float
    downbeats: list[float]
    downbeat_confidence: float


@dataclass
class Disagreement:
    """A bar whose mm:ss cross-check is more than one bar away from the bar's real start."""

    which: Literal["exit_a", "entry_b"]
    bar: int
    stated_time: str
    bar_time: float
    delta_s: float | None  # None when stated_time isn't parseable as mm:ss


@dataclass
class Score:
    """The LLM's choice vs. the user's hand-marked points for one pair."""

    marked: bool
    exit_error_bars: int | None = None
    entry_error_bars: int | None = None
    exit_error_s: float | None = None
    entry_error_s: float | None = None
    rating: int | None = None
    note: str | None = None


@dataclass
class PairResult:
    pair_id: str
    a: TrackFacts | None = None
    b: TrackFacts | None = None
    failure: str | None = None
    answer: TransitionAnswer | None = None
    exit_time: float | None = None
    entry_time: float | None = None
    disagreements: list[Disagreement] = field(default_factory=list)
    preview_path: str | None = None
    score: Score | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None
