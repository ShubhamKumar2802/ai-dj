"""Structure labels from a local LLM via common/llm_service, unchanged (spec §4.7)."""

import math
from pathlib import Path

from common.llm_service import LLMProviderError, LLMValidationError, TextRequest, get_llm_service
from common.llm_service.factory import LLMServiceConfig
from common.llm_service.prompt_manager import PromptManager
from common.logging import get_logger
from experiments.lyrics_sourcing.config import LlmConfig
from experiments.lyrics_sourcing.schema import StepError, StructureLabels, StructureResult, Timeline
from experiments.lyrics_sourcing.steps.llm import ollama_provider
from experiments.lyrics_sourcing.steps.llm.validate import validate

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_TEMPLATE = "structure_labels.txt"
CHARS_PER_TOKEN = 3.5

COLUMN_GUIDE = "\n".join(
    [
        "- t: second (row key; section boundaries must use these values)",
        "- bar: bar index covering this second (empty outside the beat grid)",
        "- downbeat: 1 if a bar starts in this second",
        "- beats: number of beats in this second",
        "- energy_lufs: loudness of the bar, LUFS (higher = louder)",
        "- vocal: vocal-band energy of the bar, 0-1 within this track",
        "- rms, low, high, centroid, flux: bar loudness, bass energy, treble energy, "
        "brightness, spectral change; each 0-1 within this track",
        "- chroma: dominant pitch class of the bar",
        "- phrase: strength of a detected phrase boundary starting in this second",
        "- cue: cue points detected here by a heuristic (e.g. hook_in, hook_exit, intro_end)",
        "- riser: 1 inside a detected build-up/riser",
        "- lyric: text of any lyric line starting in this second",
    ]
)

_logger = get_logger("ai_dj.experiments.lyrics_sourcing.llm")


class LlmServiceStructureLabeler:
    def __init__(self, cfg: LlmConfig) -> None:
        self._cfg = cfg

    def label(self, timeline: Timeline, serialized: str, serializer: str) -> StructureResult:
        cfg = self._cfg
        if cfg.provider == ollama_provider.PROVIDER_NAME:
            ollama_provider.ensure_registered()

        service = get_llm_service(
            LLMServiceConfig(
                provider=cfg.provider,
                model=cfg.model,
                base_url=cfg.base_url,
                api_key=cfg.api_key,
                # Required by LLMServiceConfig; never read on this path (no load_config).
                api_key_env_var="OLLAMA_API_KEY",
                max_concurrency=cfg.max_concurrency,
                request_timeout_s=cfg.request_timeout_s,
                cache_enabled=cfg.cache_enabled,
                cache_dir=cfg.cache_dir,
            )
        )

        prompt, prompt_version = render_prompt(timeline, serialized, serializer)
        estimated_tokens = round(len(prompt) / CHARS_PER_TOKEN)
        if estimated_tokens > cfg.context_tokens:
            _logger.warning(
                "prompt ~%d tokens exceeds llm.context_tokens=%d — start Ollama with a larger "
                "OLLAMA_CONTEXT_LENGTH or the timeline will be truncated",
                estimated_tokens,
                cfg.context_tokens,
            )

        request = TextRequest(
            prompt=prompt,
            prompt_version=prompt_version,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            timeout_s=cfg.request_timeout_s,
            metadata={"consumer": "lyrics_sourcing"},
        )
        try:
            labels = service.generate(request, StructureLabels)
        except (LLMProviderError, LLMValidationError) as exc:
            raise StepError("llm", f"{type(exc).__name__}: {exc}") from exc

        labels, issues = validate(labels, timeline.header.duration)
        return StructureResult(
            labels=labels,
            issues=issues,
            model=cfg.model,
            prompt_version=prompt_version,
            estimated_tokens=estimated_tokens,
            serializer=serializer,
        )


def render_prompt(timeline: Timeline, serialized: str, serializer: str) -> tuple[str, str]:
    return PromptManager(prompts_dir=PROMPTS_DIR).render(
        PROMPT_TEMPLATE,
        serializer_name=serializer.upper(),
        column_guide=COLUMN_GUIDE,
        max_t=str(math.floor(timeline.header.duration)),
        duration=f"{timeline.header.duration:.1f}",
        timeline=serialized,
    )
