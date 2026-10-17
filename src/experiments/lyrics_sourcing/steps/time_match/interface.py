from typing import Protocol

from experiments.lyrics_sourcing.schema import (
    IngestedTrack,
    LyricsCandidate,
    SyncedLyrics,
    Transcript,
)


class TimeMatcher(Protocol):
    def match(
        self,
        track: IngestedTrack,
        candidates: list[LyricsCandidate],
        transcript: Transcript,
    ) -> SyncedLyrics: ...
