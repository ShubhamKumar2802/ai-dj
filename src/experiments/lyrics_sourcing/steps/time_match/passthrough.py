"""Baseline / swap target: trust the first synced candidate's timing as-is (spec §4.4).

Ignores the transcript for validation; uses it only when nothing synced was fetched.
"""

from experiments.lyrics_sourcing.config import TimeMatchConfig
from experiments.lyrics_sourcing.schema import (
    IngestedTrack,
    LyricsCandidate,
    SyncedLyrics,
    Transcript,
)
from experiments.lyrics_sourcing.steps.time_match.resolve import (
    transcript_lyrics,
    unshifted_lyrics,
)


class PassthroughMatcher:
    def __init__(self, cfg: TimeMatchConfig) -> None:
        self._cfg = cfg

    def match(
        self,
        track: IngestedTrack,
        candidates: list[LyricsCandidate],
        transcript: Transcript,
    ) -> SyncedLyrics:
        for candidate in candidates:
            if candidate.status == "synced":
                return unshifted_lyrics(candidate, track.duration, self._cfg, [])
        return transcript_lyrics(transcript, self._cfg, [])
