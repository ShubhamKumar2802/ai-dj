from acquisition.youtube_downloader.config import DownloadConfig
from acquisition.youtube_downloader.downloader_ytdlp import YtDlpDownloader
from acquisition.youtube_downloader.interface import Downloader
from acquisition.youtube_downloader.manifest import (
    ManifestEntry,
    _utcnow_iso,
    read_manifest_entry,
    write_manifest_entry,
)
from acquisition.youtube_downloader.schema import DownloadedTrack, DownloadFailure
from acquisition.youtube_downloader.video_id import extract_video_id

_default_downloader: Downloader = YtDlpDownloader()


def _download_one(
    url: str,
    config: DownloadConfig,
    run_id: str,
    _downloader: Downloader = _default_downloader,
) -> DownloadedTrack | DownloadFailure:
    video_id = extract_video_id(url)
    if video_id is not None:
        cached = read_manifest_entry(video_id, config)
        if cached is not None:
            return DownloadedTrack(
                url=url,
                path=cached.path,
                video_id=cached.video_id,
                title=cached.title,
                uploader=cached.uploader,
                duration=cached.duration,
            )

    try:
        info = _downloader.run(url, config)
        write_manifest_entry(
            ManifestEntry(
                video_id=info.video_id,
                path=info.path,
                title=info.title,
                uploader=info.uploader,
                duration=info.duration,
                first_run_id=run_id,
                downloaded_at=_utcnow_iso(),
            ),
            config,
        )
        return DownloadedTrack(
            url=url,
            path=info.path,
            video_id=info.video_id,
            title=info.title,
            uploader=info.uploader,
            duration=info.duration,
        )
    except Exception as exc:
        return DownloadFailure(url=url, error=str(exc), error_type=type(exc).__name__)
