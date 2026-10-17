from typing import Protocol

from experiments.lyrics_sourcing.schema import IngestedTrack, TrackMetadata


class MetadataExtractor(Protocol):
    def extract(self, track: IngestedTrack) -> TrackMetadata: ...
