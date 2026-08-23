import os
from pathlib import Path

import yt_dlp

from acquisition.youtube_downloader.config import DownloadConfig
from acquisition.youtube_downloader.interface import DownloadInfo


class YtDlpDownloader:
    def run(self, url: str, config: DownloadConfig) -> DownloadInfo:
        options = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(config.output_dir, config.filename_template),
            "noplaylist": True,
            "retries": config.retries,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": config.audio_format,
                    "preferredquality": config.audio_quality,
                },
                *([{"key": "FFmpegMetadata"}] if config.embed_metadata else []),
            ],
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            raw_path = ydl.prepare_filename(info)

        # yt-dlp's own recommended mechanism: outtmpl's rendered path still
        # carries the pre-conversion extension — FFmpegExtractAudio swaps the
        # real on-disk extension after download.
        path = Path(raw_path).with_suffix(f".{config.audio_format}")

        return DownloadInfo(
            path=str(path),
            video_id=info["id"],
            title=info["title"],
            uploader=info.get("uploader"),
            duration=float(info["duration"]),
        )
