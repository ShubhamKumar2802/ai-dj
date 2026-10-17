from typing import Protocol

from experiments.lyrics_sourcing.schema import IngestedTrack, Transcript


class Transcriber(Protocol):
    def transcribe(self, track: IngestedTrack) -> Transcript: ...
