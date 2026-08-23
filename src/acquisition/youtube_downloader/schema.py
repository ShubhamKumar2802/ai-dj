from dataclasses import dataclass


@dataclass
class DownloadedTrack:
    url: str
    path: str
    video_id: str
    title: str
    uploader: str | None
    duration: float


@dataclass
class DownloadFailure:
    url: str
    error: str
    error_type: str


@dataclass
class DownloadResult:
    tracks: list[DownloadedTrack]
    failures: list[DownloadFailure]
    run_id: str
