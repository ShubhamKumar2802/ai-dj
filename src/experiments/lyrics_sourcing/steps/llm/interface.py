from typing import Protocol

from experiments.lyrics_sourcing.schema import StructureResult, Timeline


class StructureLabeler(Protocol):
    def label(self, timeline: Timeline, serialized: str, serializer: str) -> StructureResult: ...
