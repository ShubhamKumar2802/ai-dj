from dataclasses import dataclass
from typing import Protocol

from acquisition.youtube_downloader.config import DownloadConfig


@dataclass
class DownloadInfo:
    path: str
    video_id: str
    title: str
    uploader: str | None
    duration: float


class Downloader(Protocol):
    def run(self, url: str, config: DownloadConfig) -> DownloadInfo: ...
