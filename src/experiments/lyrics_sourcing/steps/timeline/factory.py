"""Two independently swappable parts: the builder (`impl`) and the serializer (`serializer`)."""

from collections.abc import Callable

from experiments.lyrics_sourcing.config import TimelineConfig
from experiments.lyrics_sourcing.steps import resolve_impl
from experiments.lyrics_sourcing.steps.timeline.interface import (
    TimelineBuilder,
    TimelineSerializer,
)
from experiments.lyrics_sourcing.steps.timeline.json_serializer import JsonSerializer
from experiments.lyrics_sourcing.steps.timeline.per_second import PerSecondTimelineBuilder
from experiments.lyrics_sourcing.steps.timeline.toon import ToonSerializer

_BUILDERS: dict[str, Callable[[TimelineConfig], TimelineBuilder]] = {
    "per_second": PerSecondTimelineBuilder,
}

_SERIALIZERS: dict[str, Callable[[TimelineConfig], TimelineSerializer]] = {
    "toon": ToonSerializer,
    "json": JsonSerializer,
}


def build_builder(cfg: TimelineConfig) -> TimelineBuilder:
    return resolve_impl(_BUILDERS, cfg.impl, "timeline")(cfg)


def build_serializer(cfg: TimelineConfig) -> TimelineSerializer:
    return resolve_impl(_SERIALIZERS, cfg.serializer, "timeline serializer")(cfg)
