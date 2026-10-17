from typing import Protocol

from experiments.lyrics_sourcing.schema import IngestedTrack, LyricsCandidate


class LyricsFetcher(Protocol):
    source: str  # "ytmusic" | "lrclib" | ...

    def fetch(self, track: IngestedTrack) -> list[LyricsCandidate]: ...
