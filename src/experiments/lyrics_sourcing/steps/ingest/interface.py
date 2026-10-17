from typing import Protocol

from experiments.lyrics_sourcing.schema import IngestedTrack


class TrackIngester(Protocol):
    def ingest(self, url: str) -> IngestedTrack: ...
