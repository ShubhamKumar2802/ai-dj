import pytest

from experiments.lyrics_sourcing.pipeline import build_steps
from experiments.lyrics_sourcing.steps.ingest import factory as ingest_factory
from experiments.lyrics_sourcing.steps.lyrics.lrclib import LrclibFetcher
from experiments.lyrics_sourcing.steps.lyrics.ytmusic import YtMusicFetcher
from experiments.lyrics_sourcing.steps.time_match import factory as time_match_factory
from experiments.lyrics_sourcing.steps.time_match.offset_vote import OffsetVoteMatcher
from experiments.lyrics_sourcing.steps.time_match.passthrough import PassthroughMatcher
from experiments.lyrics_sourcing.steps.timeline import factory as timeline_factory
from experiments.lyrics_sourcing.steps.timeline.json_serializer import JsonSerializer
from experiments.lyrics_sourcing.steps.timeline.toon import ToonSerializer


def test_every_default_impl_builds_without_io(cfg):
    steps = build_steps(cfg)
    assert [type(f) for f in steps.fetchers] == [YtMusicFetcher, LrclibFetcher]
    assert isinstance(steps.matcher, OffsetVoteMatcher)
    assert isinstance(steps.serializer, ToonSerializer)


def test_swapping_impl_returns_the_other_class(cfg):
    cfg.time_match.impl = "passthrough"
    assert isinstance(time_match_factory.build(cfg.time_match), PassthroughMatcher)
    cfg.timeline.serializer = "json"
    assert isinstance(timeline_factory.build_serializer(cfg.timeline), JsonSerializer)


def test_unknown_impl_lists_valid_names(cfg):
    cfg.ingest.impl = "soundcloud"
    with pytest.raises(ValueError, match="unknown ingest impl 'soundcloud'; valid: youtube"):
        ingest_factory.build(cfg.ingest)


def test_lyrics_chain_order_follows_config(cfg):
    cfg.lyrics.impl = ["lrclib", "ytmusic"]
    steps = build_steps(cfg)
    assert [f.source for f in steps.fetchers] == ["lrclib", "ytmusic"]
