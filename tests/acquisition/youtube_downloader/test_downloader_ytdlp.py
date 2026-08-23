import acquisition.youtube_downloader.downloader_ytdlp as downloader_ytdlp_module
from acquisition.youtube_downloader.config import DownloadConfig
from acquisition.youtube_downloader.downloader_ytdlp import YtDlpDownloader

_DEFAULT_INFO = {
    "id": "abc123",
    "title": "Some Title",
    "uploader": "Some Uploader",
    "duration": 180.0,
}


class _FakeYoutubeDL:
    last_options = None
    info = _DEFAULT_INFO
    prepared_filename = "music/Some Title [abc123].webm"

    def __init__(self, options):
        _FakeYoutubeDL.last_options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download):
        assert download is True
        return self.info

    def prepare_filename(self, info):
        return self.prepared_filename


def _patch_ytdlp(monkeypatch):
    monkeypatch.setattr(downloader_ytdlp_module.yt_dlp, "YoutubeDL", _FakeYoutubeDL)


def test_options_dict_shape_with_metadata_embedding(monkeypatch):
    _patch_ytdlp(monkeypatch)
    config = DownloadConfig(embed_metadata=True, retries=5)

    YtDlpDownloader().run("https://youtu.be/abc123", config)

    options = _FakeYoutubeDL.last_options
    assert options["format"] == "bestaudio/best"
    assert options["outtmpl"] == "music/%(title)s [%(id)s].%(ext)s"
    assert options["noplaylist"] is True
    assert options["retries"] == 5
    assert options["postprocessors"] == [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"},
        {"key": "FFmpegMetadata"},
    ]


def test_options_dict_omits_metadata_postprocessor_when_disabled(monkeypatch):
    _patch_ytdlp(monkeypatch)
    config = DownloadConfig(embed_metadata=False)

    YtDlpDownloader().run("https://youtu.be/abc123", config)

    options = _FakeYoutubeDL.last_options
    assert options["postprocessors"] == [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"},
    ]


def test_resolves_final_path_by_swapping_extension(monkeypatch):
    _patch_ytdlp(monkeypatch)
    monkeypatch.setattr(_FakeYoutubeDL, "prepared_filename", "music/Some Title [abc123].webm")
    config = DownloadConfig(audio_format="mp3")

    info = YtDlpDownloader().run("https://youtu.be/abc123", config)

    assert info.path == "music/Some Title [abc123].mp3"


def test_resolves_final_path_with_dotted_title(monkeypatch):
    _patch_ytdlp(monkeypatch)
    monkeypatch.setattr(_FakeYoutubeDL, "prepared_filename", "music/Track Vol. 2 [abc123].webm")
    config = DownloadConfig(audio_format="mp3")

    info = YtDlpDownloader().run("https://youtu.be/abc123", config)

    assert info.path == "music/Track Vol. 2 [abc123].mp3"


def test_maps_info_dict_fields(monkeypatch):
    _patch_ytdlp(monkeypatch)
    config = DownloadConfig()

    info = YtDlpDownloader().run("https://youtu.be/abc123", config)

    assert info.video_id == "abc123"
    assert info.title == "Some Title"
    assert info.uploader == "Some Uploader"
    assert info.duration == 180.0


def test_missing_uploader_maps_to_none(monkeypatch):
    _patch_ytdlp(monkeypatch)
    info_without_uploader = {k: v for k, v in _DEFAULT_INFO.items() if k != "uploader"}
    monkeypatch.setattr(_FakeYoutubeDL, "info", info_without_uploader)
    config = DownloadConfig()

    info = YtDlpDownloader().run("https://youtu.be/abc123", config)

    assert info.uploader is None
