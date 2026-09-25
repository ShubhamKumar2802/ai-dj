"""LLM-based structural boundary detection — a deliberately different
approach from `cue_derivation`'s `hook_in`/`hook_exit` energy+vocal-threshold
heuristic, testing T8/Q7's hypothesis that the heuristic is too crude a proxy
for "the chorus." Not part of the main pipeline — consumed only by
`run_experiment.py`.
"""

import json

from pydantic import BaseModel, Field

from common.llm_service import LLMService, TextRequest
from common.llm_service.prompt_manager import PromptManager
from ingestion.feature_extractor.schema import RawFeatures
from ingestion.orchestrator.schema import Track

_MIN_CHORUS_SPAN_S = 3.0
_TEMPLATE_NAME = "structure_labels.txt"


class TrackStructureLabels(BaseModel):
    intro_end: float | None = Field(
        description="Seconds where the intro ends and the first main section begins"
    )
    chorus1_start: float | None = Field(description="Seconds where the first chorus/hook begins")
    chorus1_end: float | None = Field(description="Seconds where the first chorus/hook ends")
    outro_start: float | None = Field(
        description="Seconds where the outro/fade begins, or null if there isn't one"
    )


def detect_structure_llm(
    raw: RawFeatures,
    llm_service: LLMService,
    prompt_manager: PromptManager | None = None,
) -> TrackStructureLabels:
    """One LLM call per track. `llm_service` caches on (payload, schema,
    model, prompt_version) — re-running this for the same track/model/prompt
    version is free after the first success, so no separate caching layer is
    needed here.

    Deliberately omits `chroma_vector`/`spectral_centroid`/`high_band_energy`
    from the payload — they're most of a track's telemetry size and the
    least relevant signal for structural (not harmonic) segmentation.
    """
    prompt_manager = prompt_manager or PromptManager()
    prompt, prompt_version = prompt_manager.render(
        _TEMPLATE_NAME,
        duration=raw.duration,
        bpm=raw.bpm,
        beats_per_bar=raw.beats_per_bar,
        bar_times=json.dumps([round(b.start_time, 2) for b in raw.per_bar_features]),
        rms=json.dumps([round(b.rms, 4) for b in raw.per_bar_features]),
        spectral_flux=json.dumps([round(b.spectral_flux, 4) for b in raw.per_bar_features]),
        low_band_energy=json.dumps([round(b.low_band_energy, 4) for b in raw.per_bar_features]),
        vocal_band_energy=json.dumps([round(v, 2) for v in raw.vocal_band_energy]),
    )
    request = TextRequest(
        prompt=prompt,
        prompt_version=prompt_version,
        timeout_s=90.0,
        max_tokens=300,
        metadata={"consumer": "llm_camelot_sequencer"},
    )
    return llm_service.generate(request, TrackStructureLabels)


def validate_structure_labels(
    labels: TrackStructureLabels,
    track: Track,
    min_play_seconds: float = 8.0,
) -> TrackStructureLabels | None:
    """Clamps and sanity-checks an LLM's raw output against the track it
    describes. Returns None (caller excludes the track, logs why) rather
    than raising — matches this codebase's "one bad item never crashes the
    batch" convention (`ingestion.orchestrator`'s `IngestionFailure`,
    `Track.status`).

    - Every value clamped to [0, track.duration].
    - `intro_end` falls back to the already-reliable, cue_derivation-computed
      `track.free_intro_end` if missing — no need to trust the LLM for a
      value that's already known.
    - Requires strict `intro_end <= chorus1_start < chorus1_end` and a
      minimum chorus span (>= 3.0s) after clamping/fallback.
    - `chorus1_end - track.grid_start` (the span every non-closer track
      actually plays, per `mix_builder.py`) must clear `min_play_seconds` —
      the same rule `path_search.feasibility.path_is_feasible` enforces
      downstream, checked here first so a bad boundary is excluded from the
      candidate pool with a clear reason instead of surfacing as a bare
      assertion failure deep in chain assembly.
    - A nonsensical `outro_start` (before `chorus1_end`) is dropped, not
      treated as a reason to exclude the whole track — it's collected but
      unused by `mix_builder.py` in this pass anyway (see that module).
    """

    def _clamp(v: float | None) -> float | None:
        if v is None:
            return None
        return max(0.0, min(v, track.duration))

    intro_end = _clamp(labels.intro_end)
    chorus1_start = _clamp(labels.chorus1_start)
    chorus1_end = _clamp(labels.chorus1_end)
    outro_start = _clamp(labels.outro_start)

    if intro_end is None:
        intro_end = track.free_intro_end

    if chorus1_start is None or chorus1_end is None:
        return None
    if not (intro_end <= chorus1_start < chorus1_end):
        return None
    if chorus1_end - chorus1_start < _MIN_CHORUS_SPAN_S:
        return None
    if chorus1_end - track.grid_start < min_play_seconds:
        return None
    if outro_start is not None and outro_start < chorus1_end:
        outro_start = None

    return TrackStructureLabels(
        intro_end=intro_end,
        chorus1_start=chorus1_start,
        chorus1_end=chorus1_end,
        outro_start=outro_start,
    )
