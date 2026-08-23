"""Shared fixture-builder helpers for acquisition/youtube_downloader's tests.

No real network, no real yt-dlp — every test here builds hand-set DownloadInfo/
ManifestEntry instances and injects a fake Downloader through the _downloader
test-seam (worker.py §3), mirroring the convention ingestion/orchestrator's own
conftest.py established for Track/Cue.
"""

import pytest

from acquisition.youtube_downloader.interface import DownloadInfo


def _make_download_info(
    path: str = "music/track.mp3",
    video_id: str = "abc123",
    title: str = "Some Title",
    uploader: str | None = "Some Uploader",
    duration: float = 180.0,
) -> DownloadInfo:
    return DownloadInfo(
        path=path, video_id=video_id, title=title, uploader=uploader, duration=duration
    )


class FakeDownloader:
    """A Downloader satisfying the Protocol structurally — records every call
    it receives, and either returns a configured DownloadInfo or raises a
    configured exception.
    """

    def __init__(self, result: DownloadInfo | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[tuple[str, object]] = []

    def run(self, url: str, config) -> DownloadInfo:
        self.calls.append((url, config))
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        return _make_download_info()


@pytest.fixture
def make_download_info():
    return _make_download_info


@pytest.fixture
def make_fake_downloader():
    return FakeDownloader
