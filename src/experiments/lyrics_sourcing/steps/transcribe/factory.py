from collections.abc import Callable

from experiments.lyrics_sourcing.config import TranscribeConfig
from experiments.lyrics_sourcing.steps import resolve_impl
from experiments.lyrics_sourcing.steps.transcribe.interface import Transcriber
from experiments.lyrics_sourcing.steps.transcribe.mlx_whisper import MlxWhisperTranscriber

_REGISTRY: dict[str, Callable[[TranscribeConfig], Transcriber]] = {
    "mlx_whisper": MlxWhisperTranscriber,
}


def build(cfg: TranscribeConfig) -> Transcriber:
    return resolve_impl(_REGISTRY, cfg.impl, "transcribe")(cfg)
