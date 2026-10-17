"""Comparison baseline for the TOON serializer, including its token count (spec §4.6)."""

import json

from experiments.lyrics_sourcing.config import TimelineConfig
from experiments.lyrics_sourcing.persistence import to_jsonable
from experiments.lyrics_sourcing.schema import Timeline


class JsonSerializer:
    extension = "json"

    def __init__(self, cfg: TimelineConfig) -> None:
        self._cfg = cfg

    def serialize(self, timeline: Timeline) -> str:
        return json.dumps(to_jsonable(timeline), indent=2, ensure_ascii=False) + "\n"
