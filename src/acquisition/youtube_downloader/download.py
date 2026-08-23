from collections.abc import Callable
from typing import Literal
from uuid import uuid4

from acquisition.youtube_downloader.config import DownloadConfig
from acquisition.youtube_downloader.schema import DownloadedTrack, DownloadFailure, DownloadResult
from acquisition.youtube_downloader.worker import _download_one

ProgressStatus = Literal["started", "completed", "failed"]
OnProgress = Callable[[str, ProgressStatus], None]


def download_tracks(
    urls: list[str],
    config: DownloadConfig,
    on_progress: OnProgress | None = None,
    *,
    _worker: Callable[
        [str, DownloadConfig, str], DownloadedTrack | DownloadFailure
    ] = _download_one,
    _run_id: str | None = None,
) -> DownloadResult:
    run_id = _run_id or str(uuid4())
    tracks: list[DownloadedTrack] = []
    failures: list[DownloadFailure] = []

    for url in urls:
        if on_progress is not None:
            on_progress(url, "started")

        result = _worker(url, config, run_id)

        if isinstance(result, DownloadedTrack):
            tracks.append(result)
            status: ProgressStatus = "completed"
        else:
            failures.append(result)
            status = "failed"

        if on_progress is not None:
            on_progress(url, status)

    return DownloadResult(tracks=tracks, failures=failures, run_id=run_id)
