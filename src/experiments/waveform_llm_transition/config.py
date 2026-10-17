"""ExperimentConfig, loaded from config.yaml.

Every field is required — config.yaml is the only place a value is declared, the same
convention the lyrics_sourcing experiment follows. Unknown keys are errors, so a typo fails
at load time rather than silently using a default.
"""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[3]
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


class BandsConfig(_Section):
    low_hz: float
    high_hz: float
    filter_order: int
    range_db: float = Field(gt=0)  # lane height window below the pair's anchor level
    smooth_beats: float = Field(gt=0)  # envelope smoothing, in beats of the track's BPM


class TilesConfig(_Section):
    tile_s: float
    overlap_s: float
    px_per_s: float
    height_px: int


class PreviewConfig(_Section):
    pre_s: float
    post_s: float


class LlmConfig(_Section):
    model: str | None
    temperature: float
    # Caps the whole reply, reasoning tokens included; None sends no cap (design.md).
    max_tokens: int | None = Field(gt=0)
    timeout_s: float = Field(gt=0)  # per-request limit; reasoning models took 128-173 s on v2


class ExperimentConfig(_Section):
    outputs_dir: str
    ground_truth: str
    pairs: list[PairConfig]
    bands: BandsConfig
    tiles: TilesConfig
    preview: PreviewConfig
    llm: LlmConfig


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> ExperimentConfig:
    with Path(path).open() as f:
        return ExperimentConfig(**yaml.safe_load(f))
