"""Whisper-validated time matching: align every synced candidate, then resolve (spec §4.4)."""

from experiments.lyrics_sourcing.config import TimeMatchConfig
from experiments.lyrics_sourcing.schema import (
    IngestedTrack,
    LyricsCandidate,
    SyncedLyrics,
    Transcript,
)
from experiments.lyrics_sourcing.steps.time_match.align import align
from experiments.lyrics_sourcing.steps.time_match.resolve import resolve


class OffsetVoteMatcher:
    def __init__(self, cfg: TimeMatchConfig) -> None:
        self._cfg = cfg

    def match(
        self,
        track: IngestedTrack,
        candidates: list[LyricsCandidate],
        transcript: Transcript,
    ) -> SyncedLyrics:
        aligned = []
        for candidate in candidates:
            if candidate.status != "synced":
                continue
            alignment, inliers = align(
                candidate.source, candidate.lines, transcript, track.duration, self._cfg
            )
            aligned.append((candidate, alignment, inliers))
        return resolve(aligned, transcript, track.duration, self._cfg)
