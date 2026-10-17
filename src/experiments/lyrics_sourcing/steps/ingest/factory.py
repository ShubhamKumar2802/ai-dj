from collections.abc import Callable

from experiments.lyrics_sourcing.config import IngestConfig
from experiments.lyrics_sourcing.steps import resolve_impl
from experiments.lyrics_sourcing.steps.ingest.interface import TrackIngester
from experiments.lyrics_sourcing.steps.ingest.youtube import YoutubeIngester

_REGISTRY: dict[str, Callable[[IngestConfig], TrackIngester]] = {
    "youtube": YoutubeIngester,
}


def build(cfg: IngestConfig) -> TrackIngester:
    return resolve_impl(_REGISTRY, cfg.impl, "ingest")(cfg)
