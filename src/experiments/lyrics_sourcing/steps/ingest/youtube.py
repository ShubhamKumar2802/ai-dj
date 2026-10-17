"""Step 1 via the production YouTube downloader, plus a yt-dlp metadata probe (spec §4.1)."""

import yt_dlp

from acquisition.youtube_downloader import DownloadConfig, download_tracks
from experiments.lyrics_sourcing.config import IngestConfig
from experiments.lyrics_sourcing.schema import IngestedTrack, StepError
from ingestion.feature_extractor.content_hash import hash_file


class YoutubeIngester:
    def __init__(self, cfg: IngestConfig) -> None:
        self._cfg = cfg

    def ingest(self, url: str) -> IngestedTrack:
        result = download_tracks([url], DownloadConfig(output_dir=self._cfg.output_dir))
        if result.failures:
            failure = result.failures[0]
            raise StepError("ingest", f"download failed ({failure.error_type}): {failure.error}")
        downloaded = result.tracks[0]

        # DownloadedTrack carries no structured song metadata, and widening a production
        # contract for an experiment is out of bounds (spec §0 invariant 1) — so probe.
        info = _probe(url)

        return IngestedTrack(
            video_id=downloaded.video_id,
            url=url,
            path=downloaded.path,
            content_hash=hash_file(downloaded.path),
            duration=downloaded.duration,
            raw_title=downloaded.title,
            title=info.get("track"),
            artist=_first_artist(info),
            album=info.get("album"),
        )


def _probe(url: str) -> dict:
    options = {"skip_download": True, "quiet": True, "no_warnings": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False) or {}


def _first_artist(info: dict) -> str | None:
    artists = info.get("artists")
    if artists:
        return artists[0]
    joined = info.get("artist") or info.get("creator")
    if not joined:
        return None
    return joined.split(",")[0].strip() or None
