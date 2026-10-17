from collections.abc import Callable

from experiments.lyrics_sourcing.config import MetadataConfig
from experiments.lyrics_sourcing.steps import resolve_impl
from experiments.lyrics_sourcing.steps.metadata.ingestion_modules import IngestionModulesExtractor
from experiments.lyrics_sourcing.steps.metadata.interface import MetadataExtractor

_REGISTRY: dict[str, Callable[[MetadataConfig], MetadataExtractor]] = {
    "ingestion_modules": IngestionModulesExtractor,
}


def build(cfg: MetadataConfig) -> MetadataExtractor:
    return resolve_impl(_REGISTRY, cfg.impl, "metadata")(cfg)
