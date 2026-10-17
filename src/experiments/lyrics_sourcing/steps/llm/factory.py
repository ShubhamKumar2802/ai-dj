from collections.abc import Callable

from experiments.lyrics_sourcing.config import LlmConfig
from experiments.lyrics_sourcing.steps import resolve_impl
from experiments.lyrics_sourcing.steps.llm.interface import StructureLabeler
from experiments.lyrics_sourcing.steps.llm.llm_service_labeler import LlmServiceStructureLabeler

_REGISTRY: dict[str, Callable[[LlmConfig], StructureLabeler]] = {
    "llm_service": LlmServiceStructureLabeler,
}


def build(cfg: LlmConfig) -> StructureLabeler:
    return resolve_impl(_REGISTRY, cfg.impl, "llm")(cfg)
