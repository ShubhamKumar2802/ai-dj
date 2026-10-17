from collections.abc import Callable

from experiments.lyrics_sourcing.config import LyricsConfig
from experiments.lyrics_sourcing.steps import resolve_impl
from experiments.lyrics_sourcing.steps.lyrics.interface import LyricsFetcher
from experiments.lyrics_sourcing.steps.lyrics.lrclib import LrclibFetcher
from experiments.lyrics_sourcing.steps.lyrics.ytmusic import YtMusicFetcher

_REGISTRY: dict[str, Callable[[LyricsConfig], LyricsFetcher]] = {
    "ytmusic": YtMusicFetcher,
    "lrclib": LrclibFetcher,
}


def build(cfg: LyricsConfig) -> list[LyricsFetcher]:
    """The fetcher chain, in `cfg.impl` (priority) order."""
    return [resolve_impl(_REGISTRY, name, "lyrics")(cfg) for name in cfg.impl]
