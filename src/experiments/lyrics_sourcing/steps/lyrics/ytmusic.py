"""YouTube Music timed lyrics, looked up from the video ID alone (spec §4.2)."""

from typing import Any

from experiments.lyrics_sourcing.config import LyricsConfig
from experiments.lyrics_sourcing.schema import IngestedTrack, LyricLine, LyricsCandidate, utc_now

SOURCE = "ytmusic"


class YtMusicFetcher:
    source = SOURCE

    def __init__(self, cfg: LyricsConfig) -> None:
        self._cfg = cfg

    def fetch(self, track: IngestedTrack) -> list[LyricsCandidate]:
        from ytmusicapi import YTMusic  # lazy: keeps factory construction I/O- and import-free

        ytmusic = YTMusic()
        browse_id = ytmusic.get_watch_playlist(videoId=track.video_id).get("lyrics")
        if not browse_id:
            return [not_found()]
        return [parse_ytmusic_lyrics(ytmusic.get_lyrics(browse_id, timestamps=True), browse_id)]


def not_found() -> LyricsCandidate:
    return LyricsCandidate(
        source=SOURCE,
        source_ref=None,
        status="not_found",
        lines=[],
        plain_text=None,
        reference_duration=None,
        error=None,
        fetched_at=utc_now(),
    )


def parse_ytmusic_lyrics(payload: dict | None, browse_id: str | None) -> LyricsCandidate:
    """Map a `get_lyrics(..., timestamps=True)` payload to a candidate. Pure.

    Timed lines may be ytmusicapi `LyricLine` objects or plain dicts (recorded fixtures);
    both expose `text` / `start_time` / `end_time` (milliseconds).
    """
    if not payload or not payload.get("lyrics"):
        candidate = not_found()
        candidate.source_ref = browse_id
        return candidate

    lyrics = payload["lyrics"]
    if payload.get("hasTimestamps") and isinstance(lyrics, list):
        lines = []
        for item in lyrics:
            text = (_field(item, "text") or "").strip()
            start_ms = _field(item, "start_time")
            if not text or start_ms is None:
                continue
            end_ms = _field(item, "end_time")
            lines.append(
                LyricLine(
                    start=start_ms / 1000,
                    end=end_ms / 1000 if end_ms is not None else None,
                    text=text,
                )
            )
        lines.sort(key=lambda line: line.start)
        if lines:
            return LyricsCandidate(
                source=SOURCE,
                source_ref=browse_id,
                status="synced",
                lines=lines,
                plain_text=None,
                reference_duration=None,
                error=None,
                fetched_at=utc_now(),
            )
        lyrics = "\n".join((_field(item, "text") or "") for item in lyrics)

    return LyricsCandidate(
        source=SOURCE,
        source_ref=browse_id,
        status="plain_only",
        lines=[],
        plain_text=str(lyrics),
        reference_duration=None,
        error=None,
        fetched_at=utc_now(),
    )


def _field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)
