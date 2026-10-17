from collections.abc import Callable

from experiments.lyrics_sourcing.config import TimeMatchConfig
from experiments.lyrics_sourcing.steps import resolve_impl
from experiments.lyrics_sourcing.steps.time_match.interface import TimeMatcher
from experiments.lyrics_sourcing.steps.time_match.offset_vote import OffsetVoteMatcher
from experiments.lyrics_sourcing.steps.time_match.passthrough import PassthroughMatcher

_REGISTRY: dict[str, Callable[[TimeMatchConfig], TimeMatcher]] = {
    "offset_vote": OffsetVoteMatcher,
    "passthrough": PassthroughMatcher,
}


def build(cfg: TimeMatchConfig) -> TimeMatcher:
    return resolve_impl(_REGISTRY, cfg.impl, "time_match")(cfg)
