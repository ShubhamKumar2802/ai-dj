import pytest

import acquisition.youtube_downloader.playlist as playlist_module
from acquisition.youtube_downloader.config import DownloadConfig
from acquisition.youtube_downloader.playlist import expand_playlist_url, extract_playlist_id

_LIST_ID = "PLjxsdvPZH24OZoxZSnuEqrW1crVtceCNG"

_RECOGNIZED = [
    f"https://www.youtube.com/watch?v=7KKVb0_IdD4&list={_LIST_ID}",
    f"https://youtube.com/watch?v=7KKVb0_IdD4&list={_LIST_ID}",
    f"https://www.youtube.com/playlist?list={_LIST_ID}",
    f"https://www.youtube.com/watch?v=7KKVb0_IdD4&list={_LIST_ID}&index=5",
]

_UNRECOGNIZED = [
    "https://www.youtube.com/watch?v=7KKVb0_IdD4",
    "https://youtu.be/7KKVb0_IdD4",
    f"https://music.youtube.com/playlist?list={_LIST_ID}",
    "",
    "not a url",
]


@pytest.mark.parametrize("url", _RECOGNIZED)
def test_recognized_shapes_extract_the_list_id(url):
    assert extract_playlist_id(url) == _LIST_ID


@pytest.mark.parametrize("url", _UNRECOGNIZED)
def test_unrecognized_shapes_return_none(url):
    assert extract_playlist_id(url) is None


class _FakeYoutubeDL:
    last_options = None
    constructed = False
    info = {"_type": "playlist", "entries": []}

    def __init__(self, options):
        _FakeYoutubeDL.last_options = options
        _FakeYoutubeDL.constructed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download):
        assert download is False
        return self.info


def _patch_ytdlp(monkeypatch):
    monkeypatch.setattr(_FakeYoutubeDL, "constructed", False)
    monkeypatch.setattr(playlist_module.yt_dlp, "YoutubeDL", _FakeYoutubeDL)


def test_expand_returns_entry_urls_in_order(monkeypatch):
    _patch_ytdlp(monkeypatch)
    entries = [
        {"id": "a", "url": "https://www.youtube.com/watch?v=a"},
        {"id": "b", "url": "https://www.youtube.com/watch?v=b"},
    ]
    monkeypatch.setattr(_FakeYoutubeDL, "info", {"_type": "playlist", "entries": entries})

    result = expand_playlist_url(
        f"https://www.youtube.com/playlist?list={_LIST_ID}", DownloadConfig()
    )

    assert result == [
        "https://www.youtube.com/watch?v=a",
        "https://www.youtube.com/watch?v=b",
    ]


def test_expand_filters_out_none_entries(monkeypatch):
    _patch_ytdlp(monkeypatch)
    entries = [{"id": "a", "url": "https://www.youtube.com/watch?v=a"}, None]
    monkeypatch.setattr(_FakeYoutubeDL, "info", {"_type": "playlist", "entries": entries})

    result = expand_playlist_url(
        f"https://www.youtube.com/playlist?list={_LIST_ID}", DownloadConfig()
    )

    assert result == ["https://www.youtube.com/watch?v=a"]


def test_expand_empty_playlist_returns_empty_list_not_none(monkeypatch):
    _patch_ytdlp(monkeypatch)
    monkeypatch.setattr(_FakeYoutubeDL, "info", {"_type": "playlist", "entries": []})

    result = expand_playlist_url(
        f"https://www.youtube.com/playlist?list={_LIST_ID}", DownloadConfig()
    )

    assert result == []


def test_expand_non_playlist_url_returns_none_without_calling_ytdlp(monkeypatch):
    _patch_ytdlp(monkeypatch)

    result = expand_playlist_url("https://www.youtube.com/watch?v=7KKVb0_IdD4", DownloadConfig())

    assert result is None
    assert _FakeYoutubeDL.constructed is False


def test_expand_passes_retries_to_options(monkeypatch):
    _patch_ytdlp(monkeypatch)
    monkeypatch.setattr(_FakeYoutubeDL, "info", {"_type": "playlist", "entries": []})

    expand_playlist_url(
        f"https://www.youtube.com/playlist?list={_LIST_ID}", DownloadConfig(retries=7)
    )

    assert _FakeYoutubeDL.last_options["retries"] == 7
