"""ExperimentConfig, loaded from config.yaml.

Every field is required — config.yaml is the only place a value is declared, the same
convention the waveform_llm_transition experiment follows. Unknown keys are errors, so a
typo fails at load time rather than silently using a default.
"""

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

_YOUTUBE_ID = re.compile(r"\[([A-Za-z0-9_-]{6,})\]")


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrackConfig(_Section):
    name: str
    path: str

    @property
    def track_id(self) -> str:
        """The `[youtube id]` suffix of the filename, else the file stem."""
        match = _YOUTUBE_ID.search(Path(self.path).name)
        return match.group(1) if match else Path(self.path).stem


class PairConfig(_Section):
    a: TrackConfig
    b: TrackConfig

    @property
    def pair_id(self) -> str:
        return f"{self.a.track_id}__{self.b.track_id}"

    def missing_paths(self) -> list[str]:
        """Configured audio paths that don't exist, relative to the current directory."""
        return [t.path for t in (self.a, self.b) if not Path(t.path).is_file()]


class SeparatorConfig(_Section):
    model: str
    shifts: int = Field(ge=0)
    overlap: float = Field(ge=0, lt=1)
    device: Literal["auto", "mps", "cpu"]
    cache_dir: str

    @property
    def separator_version(self) -> str:
        """Part of the stem cache key (design.md). Bump the trailing `v1` by hand when the
        pre- or post-processing in separation.py changes."""
        return f"{self.model}|shifts={self.shifts}|overlap={self.overlap}|v1"


class WindowsConfig(_Section):
    threshold_db: float = Field(gt=0)
    floor_dbfs: float
    min_bars: int = Field(ge=1)


class RenderConfig(_Section):
    overlap_bars: int = Field(ge=1)
    bass_swap_bars: int = Field(ge=2)
    crossover_hz: float = Field(gt=0)
    match_loudness: bool

    @field_validator("bass_swap_bars")
    @classmethod
    def _even(cls, value: int) -> int:
        if value % 2:
            raise ValueError("bass_swap_bars must be even (the bass swaps on the halfway downbeat)")
        return value


class ExperimentConfig(_Section):
    outputs_dir: str
    ground_truth: str
    pair: PairConfig
    separator: SeparatorConfig
    windows: WindowsConfig
    exit_after_bar: int = Field(ge=0)
    render: RenderConfig


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> ExperimentConfig:
    with Path(path).open() as f:
        return ExperimentConfig(**yaml.safe_load(f))
