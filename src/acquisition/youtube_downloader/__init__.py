from acquisition.youtube_downloader.config import DownloadConfig
from acquisition.youtube_downloader.download import download_tracks
from acquisition.youtube_downloader.playlist import expand_playlist_url
from acquisition.youtube_downloader.schema import DownloadedTrack, DownloadFailure, DownloadResult

__all__ = [
    "DownloadedTrack",
    "DownloadResult",
    "DownloadFailure",
    "DownloadConfig",
    "download_tracks",
    "expand_playlist_url",
]
