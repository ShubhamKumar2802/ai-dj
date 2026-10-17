"""ExperimentConfig: one pydantic sub-model per step, loaded from config.yaml (spec §3.2).

Every field is required — config.yaml is the only place a value is declared, the same
convention `common/llm_service`'s LLMServiceConfig follows. Unknown keys are errors, so a
typo fails at load time rather than silently using nothing.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestConfig(_Section):
    impl: str
    output_dir: str


class LyricsConfig(_Section):
    impl: list[str]
    cache_dir: str
    lrclib_base_url: str
    lrclib_user_agent: str
    lrclib_max_candidates: int
    lrclib_min_interval_s: float


class TranscribeConfig(_Section):
    impl: str
    model: str
    language: str | None
    models_dir: str
    cache_dir: str


class TimeMatchConfig(_Section):
    impl: str
    min_line_chars: int
    k_candidates: int
    anchor_min_score: float
    offset_bin_s: float
    inlier_tolerance_s: float
    min_anchorable_lines: int
    min_coverage: float
    max_residual_s: float
    zero_offset_tolerance_s: float
    min_transcript_wpm: float
    max_line_s: float
    write_click_track: bool

    def thresholds(self) -> dict[str, float]:
        """The numeric knobs in force, recorded on every SyncedLyrics (spec §4.4.3)."""
        return {
            name: float(value)
            for name, value in self.model_dump().items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }


class MetadataConfig(_Section):
    impl: str


class TimelineConfig(_Section):
    impl: str
    serializer: str


class LlmConfig(_Section):
    impl: str
    provider: str
    model: str
    base_url: str
    api_key: str
    temperature: float
    max_tokens: int
    request_timeout_s: float
    max_concurrency: int
    context_tokens: int
    cache_enabled: bool
    cache_dir: str


class ExperimentConfig(_Section):
    outputs_dir: str
    ingest: IngestConfig
    lyrics: LyricsConfig
    transcribe: TranscribeConfig
    time_match: TimeMatchConfig
    metadata: MetadataConfig
    timeline: TimelineConfig
    llm: LlmConfig


def load_config(path: str | Path | None = None) -> ExperimentConfig:
    resolved = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with resolved.open() as f:
        data = yaml.safe_load(f) or {}
    return ExperimentConfig.model_validate(data)
