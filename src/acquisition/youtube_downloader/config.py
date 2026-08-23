from dataclasses import dataclass


@dataclass
class DownloadConfig:
    output_dir: str = "music"
    audio_format: str = "mp3"
    audio_quality: str = "0"
    filename_template: str = "%(title)s [%(id)s].%(ext)s"
    embed_metadata: bool = True
    retries: int = 3
    manifest_dir: str = ".cache/youtube_downloader"
