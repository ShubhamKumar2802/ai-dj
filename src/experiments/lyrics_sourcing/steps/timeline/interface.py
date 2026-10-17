from typing import Protocol

from experiments.lyrics_sourcing.schema import IngestedTrack, SyncedLyrics, Timeline, TrackMetadata


class TimelineBuilder(Protocol):
    def build(
        self, track: IngestedTrack, lyrics: SyncedLyrics, meta: TrackMetadata
    ) -> Timeline: ...


class TimelineSerializer(Protocol):
    extension: str  # "toon" | "json"

    def serialize(self, timeline: Timeline) -> str: ...
